"""Run and monitor Python scripts as child processes."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import pstats
import subprocess
import sqlite3
import sys
import tempfile
from time import monotonic
import time
from typing import Optional, Sequence

import psutil

from pylens.config.settings import Settings
from pylens.core.classifier import classify_execution
from pylens.database.connection import connect
from pylens.database.repository import ExecutionRepository, utc_now
from pylens.monitoring.monitor import ProcessMonitor
from pylens.monitoring.profiler import build_profile_command, format_profile_summary


@dataclass(frozen=True)
class RunResult:
    execution_id: int
    status: str
    classification: str
    exit_code: Optional[int]
    duration_seconds: float
    stdout: str
    stderr: str
    profile_summary: Optional[str] = None
    classification_reasons: tuple[str, ...] = ()


_OUTPUT_LIMIT_BYTES = 1024 * 1024


def _utc_timestamp() -> str:
    """### O que faz
    Cria um timestamp UTC em ISO 8601 com precisão de milissegundos.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _read_output(file_object) -> str:
    """### O que faz
    Lê a saída temporária, mantendo no máximo seu último 1 MiB.
    """
    file_object.flush()
    file_object.seek(0, os.SEEK_END)
    size = file_object.tell()
    file_object.seek(max(0, size - _OUTPUT_LIMIT_BYTES))
    text = file_object.read().decode(errors="replace")
    if size > _OUTPUT_LIMIT_BYTES:
        return "[Earlier output omitted; showing the last 1 MiB.]\n" + text
    return text


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """### O que faz
    Tenta encerrar o processo principal e seus filhos, forçando os que restarem.
    """
    try:
        parent = psutil.Process(process.pid)
        members = [parent, *parent.children(recursive=True)]
    except psutil.Error:
        members = []
        parent = None

    for member in reversed(members):
        try:
            member.terminate()
        except psutil.Error:
            pass

    _, alive = psutil.wait_procs(members, timeout=2) if members else ([], [])
    for member in alive:
        try:
            member.kill()
        except psutil.Error:
            pass
    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        except OSError:
            if process.poll() is None:
                process.kill()
                process.wait()


def run_script(
    script_path: str,
    arguments: Sequence[str] = (),
    *,
    settings: Optional[Settings] = None,
    working_directory: Optional[str] = None,
) -> RunResult:
    """### O que faz
    Executa um script, monitora recursos e grava amostras e eventos no SQLite.

    ### Parâmetros
    `script_path` indica o arquivo; `arguments` são repassados ao script;
    `settings` define os limites; `working_directory` define o diretório de execução.

    ### Retorno
    Um `RunResult` com status, duração, saídas e resumo do perfil, se houver.
    """
    settings = settings or Settings()
    script = Path(script_path).expanduser().resolve(strict=True)
    if not script.is_file():
        raise ValueError("script_path must point to a file")

    workdir = Path(working_directory).expanduser().resolve() if working_directory else Path.cwd()
    if not workdir.is_dir():
        raise ValueError("working_directory must point to a directory")

    database_path = settings.effective_database_path
    connection = connect(database_path)
    repository = ExecutionRepository(connection)
    started_at = _utc_timestamp()
    run_started_clock = monotonic()
    started_clock = None
    effective_configuration = {
        "mode": settings.mode,
        "sample_interval_seconds": settings.sample_interval_seconds,
        "timeout_seconds": settings.timeout_seconds,
        "memory_limit_bytes": settings.memory_limit_bytes,
        "cpu_limit_percent": settings.cpu_limit_percent,
        "working_directory": str(workdir),
        "profiling": settings.mode in ("detailed", "deep"),
        "line_profiling_available": settings.mode == "deep",
    }
    execution_id = repository.create_execution(
        script_path=str(script),
        arguments=list(arguments),
        mode=settings.mode,
        started_at=started_at,
        timeout_seconds=settings.timeout_seconds,
        memory_limit_bytes=settings.memory_limit_bytes,
        configuration=effective_configuration,
    )

    process = None
    status = "INTERNAL_ERROR"
    classification = "INDETERMINED"
    exit_code = None
    error_summary = None
    stdout = ""
    stderr = ""
    profile_summary = None
    sample_count = 0
    peak_cpu_percent = None
    peak_memory_bytes = None
    monitoring_complete = True
    monitoring_warning_logged = False
    profile_temp = None
    line_profile_temp = None
    try:
        repository.add_log(
            execution_id,
            level="INFO",
            event_type="EXECUTION_STARTED",
            message="Target script execution started.",
            details={"pid": None, "mode": settings.mode},
        )
        if settings.mode in ("detailed", "deep"):
            profile_temp = tempfile.NamedTemporaryFile(suffix=".prof", delete=False)
            profile_temp.close()
            line_profile_path = None
            if settings.mode == "deep":
                line_profile_temp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
                line_profile_path = line_profile_temp.name
                line_profile_temp.close()
            command = build_profile_command(
                script,
                arguments,
                mode=settings.mode,
                function_output_path=profile_temp.name,
                line_output_path=line_profile_path,
            )
        else:
            command = (sys.executable, str(script), *(str(arg) for arg in arguments))

        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            started_clock = monotonic()
            process = subprocess.Popen(
                command,
                cwd=str(workdir),
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=(os.name != "nt"),
                creationflags=creation_flags,
            )
            repository.set_pid(execution_id, process.pid)
            monitor = ProcessMonitor(process.pid)
            stop_reason = None
            last_elapsed_ms = -1

            while process.poll() is None:
                elapsed = monotonic() - started_clock
                sample = monitor.sample()
                elapsed_ms = max(int(elapsed * 1000), last_elapsed_ms + 1)
                last_elapsed_ms = elapsed_ms
                repository.add_sample(
                    execution_id,
                    collected_at=utc_now(),
                    elapsed_ms=elapsed_ms,
                    cpu_percent=sample.cpu_percent,
                    memory_rss_bytes=sample.memory_rss_bytes,
                    memory_vms_bytes=sample.memory_vms_bytes,
                    child_memory_rss_bytes=sample.child_memory_rss_bytes,
                    thread_count=sample.thread_count,
                    process_count=sample.process_count,
                )
                sample_count += 1
                if sample.cpu_percent is not None:
                    peak_cpu_percent = (
                        sample.cpu_percent
                        if peak_cpu_percent is None
                        else max(peak_cpu_percent, sample.cpu_percent)
                    )
                if sample.memory_rss_bytes is not None:
                    peak_memory_bytes = (
                        sample.memory_rss_bytes
                        if peak_memory_bytes is None
                        else max(peak_memory_bytes, sample.memory_rss_bytes)
                    )
                monitoring_complete = (
                    monitoring_complete and sample.process_tree_complete
                )
                if not sample.process_tree_complete and not monitoring_warning_logged:
                    repository.add_log(
                        execution_id,
                        level="WARNING",
                        event_type="RESOURCE_SAMPLE_INCOMPLETE",
                        message=(
                            "A complete process-tree sample was unavailable; "
                            "resource metrics for that interval were recorded as unknown."
                        ),
                        elapsed_ms=elapsed_ms,
                    )
                    monitoring_warning_logged = True

                if process.poll() is not None:
                    break

                if (
                    sample.memory_rss_bytes is not None
                    and sample.memory_rss_bytes >= settings.memory_limit_bytes
                ):
                    stop_reason = "MEMORY_LIMIT"
                    repository.add_log(
                        execution_id,
                        level="WARNING",
                        event_type="MEMORY_LIMIT_REACHED",
                        message="The configured process-tree memory limit was reached.",
                        details={
                            "observed_bytes": sample.memory_rss_bytes,
                            "limit_bytes": settings.memory_limit_bytes,
                        },
                        elapsed_ms=elapsed_ms,
                    )
                    break

                if (
                    sample.cpu_percent is not None
                    and sample.cpu_percent >= settings.cpu_limit_percent
                ):
                    stop_reason = "CPU_LIMIT"
                    repository.add_log(
                        execution_id,
                        level="WARNING",
                        event_type="CPU_LIMIT_REACHED",
                        message="The configured process-tree CPU limit was reached.",
                        details={
                            "observed_percent": sample.cpu_percent,
                            "limit_percent": settings.cpu_limit_percent,
                        },
                        elapsed_ms=elapsed_ms,
                    )
                    break

                if elapsed >= settings.timeout_seconds:
                    stop_reason = "TIMEOUT"
                    repository.add_log(
                        execution_id,
                        level="WARNING",
                        event_type="TIMEOUT_REACHED",
                        message="The configured execution timeout was reached.",
                        details={"timeout_seconds": settings.timeout_seconds},
                        elapsed_ms=elapsed_ms,
                    )
                    break

                remaining = settings.timeout_seconds - elapsed
                time.sleep(min(settings.sample_interval_seconds, max(0, remaining)))

            if stop_reason is not None:
                _terminate_process_tree(process)
                status = stop_reason
            else:
                exit_code = process.wait()
                status = "COMPLETED" if exit_code == 0 else "FAILED"

            stdout = _read_output(stdout_file)
            stderr = _read_output(stderr_file)
            if status == "FAILED":
                error_summary = stderr[-4000:] or "Target script exited with a non-zero status."
                repository.add_log(
                    execution_id,
                    level="ERROR",
                    event_type="TARGET_FAILED",
                    message="Target script exited with a non-zero status.",
                    details={"exit_code": exit_code},
                )

        if settings.mode in ("detailed", "deep") and profile_temp is not None:
            try:
                profile_summary = format_profile_summary(
                    settings.mode,
                    profile_temp.name,
                    line_profile_temp.name if line_profile_temp is not None else None,
                )
                repository.add_log(
                    execution_id,
                    level="INFO",
                    event_type="PROFILE_SUMMARY",
                    message="Function profile collected."
                    if settings.mode == "detailed"
                    else "Function and line profiles collected.",
                    details={"summary": profile_summary},
                )
            except (OSError, pstats.StatsError, ValueError) as error:
                repository.add_log(
                    execution_id,
                    level="WARNING",
                    event_type="PROFILE_INCOMPLETE",
                    message="Detailed profiling was unavailable; basic monitoring completed.",
                    details={"error": str(error)},
                )
    except KeyboardInterrupt:
        status = "INTERRUPTED"
        if process is not None and process.poll() is None:
            _terminate_process_tree(process)
        repository.add_log(
            execution_id,
            level="WARNING",
            event_type="EXECUTION_INTERRUPTED",
            message="Execution was interrupted by the user.",
        )
    except Exception as error:
        status = "INTERNAL_ERROR"
        error_summary = f"{type(error).__name__}: {error}"
        if process is not None and process.poll() is None:
            _terminate_process_tree(process)
        try:
            repository.add_log(
                execution_id,
                level="ERROR",
                event_type="PYLENS_INTERNAL_ERROR",
                message="PyLens encountered an internal error.",
                details={"error": error_summary},
            )
        except sqlite3.Error as persistence_error:
            error_summary += f"; unable to persist error log: {persistence_error}"
    finally:
        for temporary_profile in (profile_temp, line_profile_temp):
            if temporary_profile is None:
                continue
            try:
                os.unlink(temporary_profile.name)
            except FileNotFoundError:
                pass
        duration = monotonic() - (started_clock or run_started_clock)
        classification_result = classify_execution(
            status=status,
            duration_seconds=duration,
            timeout_seconds=settings.timeout_seconds,
            peak_cpu_percent=peak_cpu_percent,
            cpu_limit_percent=settings.cpu_limit_percent,
            peak_memory_bytes=peak_memory_bytes,
            memory_limit_bytes=settings.memory_limit_bytes,
            sample_count=sample_count,
            monitoring_complete=monitoring_complete,
            exit_code=exit_code,
            error_summary=error_summary,
            stderr_output=stderr,
        )
        classification = classification_result.classification
        try:
            try:
                repository.add_log(
                    execution_id,
                    level={
                        "NORMAL": "INFO",
                        "WARNING": "WARNING",
                        "CRITICAL": "ERROR",
                        "UNDETERMINED": "WARNING",
                    }[classification],
                    event_type="EXECUTION_CLASSIFIED",
                    message=f"Execution classified as {classification}.",
                    details={
                        "classification": classification,
                        "reasons": list(classification_result.reasons),
                        "peak_cpu_percent": peak_cpu_percent,
                        "peak_memory_bytes": peak_memory_bytes,
                        "duration_seconds": duration,
                    },
                )
            except sqlite3.Error:
                pass
            repository.finish_execution(
                execution_id,
                finished_at=_utc_timestamp(),
                duration_ms=int(duration * 1000),
                status=status,
                classification=classification,
                exit_code=exit_code,
                error_summary=error_summary,
            )
        finally:
            connection.close()

    return RunResult(
        execution_id=execution_id,
        status=status,
        classification=classification,
        exit_code=exit_code,
        duration_seconds=duration,
        stdout=stdout,
        stderr=stderr,
        profile_summary=profile_summary,
        classification_reasons=classification_result.reasons,
    )
