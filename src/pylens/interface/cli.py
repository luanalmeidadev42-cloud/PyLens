"""Command-line interface for PyLens."""

import argparse
import json
import math
from pathlib import Path
import sqlite3
import sys
from typing import Optional, Sequence

from pylens.config.settings import (
    DEFAULT_CPU_LIMIT_PERCENT,
    DEFAULT_MEMORY_LIMIT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    Settings,
)
from pylens.core.executor import run_script
from pylens.database.connection import connect
from pylens.database.repository import ExecutionRepository


def _build_parser() -> argparse.ArgumentParser:
    """### O que faz
    Cria e devolve o parser com os comandos e opções aceitos pela CLI.
    """
    parser = argparse.ArgumentParser(
        prog="pylens",
        description="Run Python scripts with resource monitoring and local history.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run a Python script")
    run_parser.add_argument("script", help="path to the Python script")
    run_parser.add_argument(
        "--mode", choices=("normal", "detailed", "deep"), default="normal"
    )
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"execution timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    default_memory_mib = DEFAULT_MEMORY_LIMIT_BYTES // (1024 * 1024)
    run_parser.add_argument(
        "--memory-limit-mib",
        type=int,
        default=default_memory_mib,
        help=f"process-tree memory limit in MiB (default: {default_memory_mib})",
    )
    run_parser.add_argument(
        "--cpu-limit-percent",
        type=float,
        default=DEFAULT_CPU_LIMIT_PERCENT,
        help=f"process-tree CPU limit in percent (default: {DEFAULT_CPU_LIMIT_PERCENT:g})",
    )
    run_parser.add_argument(
        "--workdir", help="working directory for the target script (default: current directory)"
    )
    run_parser.add_argument(
        "--database",
        type=Path,
        help="local SQLite history path (default: ~/.pylens/history.sqlite3)",
    )

    history_parser = subparsers.add_parser("history", help="show recent executions")
    history_parser.add_argument("--limit", type=int, default=20)
    history_parser.add_argument("--database", type=Path)

    logs_parser = subparsers.add_parser("logs", help="show events for an execution")
    logs_parser.add_argument("execution_id", type=int)
    logs_parser.add_argument(
        "--detail",
        choices=("lite", "normal", "deep"),
        default="normal",
        help="amount of log detail to display (default: normal)",
    )
    logs_parser.add_argument("--database", type=Path)

    delete_parser = subparsers.add_parser("delete", help="delete a saved execution")
    delete_parser.add_argument("execution_id", type=int)
    delete_parser.add_argument("--database", type=Path)
    delete_parser.add_argument("--yes", action="store_true", help="skip confirmation")
    return parser


def _database_for(path: Optional[Path]):
    """### O que faz
    Abre o banco informado ou o banco padrão configurado em `Settings`.
    """
    return connect(Settings(database_path=path).effective_database_path)


def _show_history(database_path: Optional[Path], limit: int) -> int:
    """### O que faz
    Lista execuções recentes e devolve o código de saída apropriado.
    """
    if limit <= 0:
        print("pylens: error: --limit must be greater than zero", file=sys.stderr)
        return 2
    try:
        connection = _database_for(database_path)
        try:
            rows = ExecutionRepository(connection).list_executions(limit)
        finally:
            connection.close()
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"pylens: error: {error}", file=sys.stderr)
        return 2

    if not rows:
        print("No executions recorded.")
        return 0
    for row in rows:
        duration = "unknown" if row["duration_ms"] is None else f"{row['duration_ms']} ms"
        print(
            f"{row['id']}  {row['started_at']}  {row['status']}  "
            f"{row['classification']}  {duration}  {row['script_path']}"
        )
    return 0


def _show_logs(database_path: Optional[Path], execution_id: int, detail: str) -> int:
    """Display structured events for one saved execution."""
    if execution_id <= 0:
        print("pylens: error: execution ID must be greater than zero", file=sys.stderr)
        return 2
    try:
        connection = _database_for(database_path)
        try:
            repository = ExecutionRepository(connection)
            if not repository.execution_exists(execution_id):
                print(f"Execution {execution_id} was not found.", file=sys.stderr)
                return 1
            rows = repository.list_logs(execution_id)
        finally:
            connection.close()
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"pylens: error: {error}", file=sys.stderr)
        return 2

    if not rows:
        print(f"No logs recorded for execution {execution_id}.")
        return 0

    for row in rows:
        if detail == "lite":
            timestamp = f"+{row['elapsed_ms']}ms" if row["elapsed_ms"] is not None else row["recorded_at"]
            print(f"{timestamp} {row['event_type']}")
            continue

        elapsed = "" if row["elapsed_ms"] is None else f" +{row['elapsed_ms']}ms"
        print(
            f"[{row['recorded_at']}{elapsed}] {row['level']} "
            f"{row['event_type']}: {row['message']}"
        )
        if detail == "deep":
            details = json.loads(row["details_json"])
            if details:
                print(json.dumps(details, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


def _delete_execution(database_path: Optional[Path], execution_id: int, confirm: bool) -> int:
    """### O que faz
    Confirma e exclui uma execução concluída, junto com seus dados relacionados.
    """
    if execution_id <= 0:
        print("pylens: error: execution ID must be greater than zero", file=sys.stderr)
        return 2
    if not confirm:
        try:
            answer = input(f"Delete execution {execution_id} and its saved data? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("Deletion cancelled.")
            return 0

    try:
        connection = _database_for(database_path)
        try:
            deleted = ExecutionRepository(connection).delete_execution(execution_id)
        finally:
            connection.close()
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"pylens: error: {error}", file=sys.stderr)
        return 2

    if not deleted:
        print(f"Execution {execution_id} was not found or is still running.", file=sys.stderr)
        return 1
    print(f"Deleted execution {execution_id} and its samples and logs.")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """### O que faz
    Interpreta os argumentos, executa o comando escolhido e retorna seu código.

    `argv` permite fornecer argumentos diretamente; quando omitido, usa os do terminal.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--" in arguments:
        separator = arguments.index("--")
        pylens_arguments = arguments[:separator]
        script_arguments = arguments[separator + 1 :]
    else:
        pylens_arguments = arguments
        script_arguments = []

    parser = _build_parser()
    parsed = parser.parse_args(pylens_arguments)
    if parsed.command == "history":
        return _show_history(parsed.database, parsed.limit)
    if parsed.command == "logs":
        return _show_logs(parsed.database, parsed.execution_id, parsed.detail)
    if parsed.command == "delete":
        return _delete_execution(parsed.database, parsed.execution_id, parsed.yes)
    if parsed.memory_limit_mib <= 0:
        parser.error("--memory-limit-mib must be greater than zero")
    if not math.isfinite(parsed.cpu_limit_percent) or parsed.cpu_limit_percent <= 0:
        parser.error("--cpu-limit-percent must be a finite number greater than zero")

    try:
        settings = Settings(
            mode=parsed.mode,
            timeout_seconds=parsed.timeout,
            memory_limit_bytes=parsed.memory_limit_mib * 1024 * 1024,
            cpu_limit_percent=parsed.cpu_limit_percent,
            database_path=parsed.database,
        )
        result = run_script(
            parsed.script,
            script_arguments,
            settings=settings,
            working_directory=parsed.workdir,
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"pylens: error: {error}", file=sys.stderr)
        return 2

    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)

    print(
        f"PyLens execution {result.execution_id}: {result.status} "
        f"(performance: {result.classification}, {result.duration_seconds:.3f}s)"
    )
    for reason in result.classification_reasons:
        print(f"  - {reason}")
    if result.profile_summary:
        print(f"\n{result.profile_summary}")

    if result.status == "COMPLETED":
        return 0
    if result.status == "TIMEOUT":
        return 124
    if result.status == "MEMORY_LIMIT":
        return 137
    if result.status == "CPU_LIMIT":
        return 125
    if result.status == "INTERRUPTED":
        return 130
    if result.status == "FAILED" and result.exit_code is not None:
        return result.exit_code or 1
    return 1
