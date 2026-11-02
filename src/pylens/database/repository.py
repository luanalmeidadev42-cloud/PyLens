"""Persistence operations for executions, samples, and logs."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now() -> str:
    """### O que faz
    Gera a data e hora atuais em UTC no formato ISO com precisão de milissegundos.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ExecutionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        """### O que faz
        Guarda a conexão SQLite usada pelas operações deste repositório.
        """
        self.connection = connection

    def create_execution(
        self,
        *,
        script_path: str,
        arguments: list,
        mode: str,
        started_at: str,
        timeout_seconds: int,
        memory_limit_bytes: int,
        configuration: Dict[str, Any],
    ) -> int:
        """### O que faz
        Registra uma execução como `RUNNING` e devolve o ID criado.
        """
        cursor = self.connection.execute(
            """INSERT INTO executions (
                   script_path, arguments_json, mode, started_at, status,
                   classification, timeout_seconds, memory_limit_bytes,
                   configuration_json
               ) VALUES (?, ?, ?, ?, 'RUNNING', 'UNDETERMINED', ?, ?, ?)""",
            (
                script_path,
                json.dumps(arguments),
                mode,
                started_at,
                timeout_seconds,
                memory_limit_bytes,
                json.dumps(configuration, sort_keys=True),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def set_pid(self, execution_id: int, pid: int) -> None:
        """### O que faz
        Salva o PID do processo associado à execução indicada.
        """
        self.connection.execute(
            "UPDATE executions SET pid = ? WHERE id = ?", (pid, execution_id)
        )
        self.connection.commit()

    def add_sample(
        self,
        execution_id: int,
        *,
        collected_at: str,
        elapsed_ms: int,
        cpu_percent: Optional[float],
        memory_rss_bytes: Optional[int],
        memory_vms_bytes: Optional[int],
        child_memory_rss_bytes: Optional[int],
        thread_count: Optional[int],
        process_count: Optional[int],
    ) -> None:
        """### O que faz
        Insere no histórico uma amostra de recursos da árvore de processos.
        """
        self.connection.execute(
            """INSERT INTO samples (
                   execution_id, collected_at, elapsed_ms, cpu_percent,
                   memory_rss_bytes, memory_vms_bytes,
                   child_memory_rss_bytes, thread_count, process_count
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                execution_id,
                collected_at,
                elapsed_ms,
                cpu_percent,
                memory_rss_bytes,
                memory_vms_bytes,
                child_memory_rss_bytes,
                thread_count,
                process_count,
            ),
        )
        self.connection.commit()

    def add_log(
        self,
        execution_id: int,
        *,
        level: str,
        event_type: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        elapsed_ms: Optional[int] = None,
    ) -> None:
        """### O que faz
        Salva um evento ou mensagem de log associado à execução.
        """
        self.connection.execute(
            """INSERT INTO logs (
                   execution_id, recorded_at, elapsed_ms, level,
                   event_type, message, details_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                execution_id,
                utc_now(),
                elapsed_ms,
                level,
                event_type,
                message,
                json.dumps(details or {}, sort_keys=True),
            ),
        )
        self.connection.commit()

    def finish_execution(
        self,
        execution_id: int,
        *,
        finished_at: str,
        duration_ms: int,
        status: str,
        classification: str,
        exit_code: Optional[int],
        error_summary: Optional[str] = None,
    ) -> None:
        """### O que faz
        Atualiza a execução com horário final, status, duração e resultado.
        """
        self.connection.execute(
            """UPDATE executions
               SET finished_at = ?, duration_ms = ?, status = ?,
                   classification = ?, exit_code = ?, error_summary = ?
               WHERE id = ?""",
            (
                finished_at,
                duration_ms,
                status,
                classification,
                exit_code,
                error_summary,
                execution_id,
            ),
        )
        self.connection.commit()

    def list_executions(self, limit: int = 20):
        """### O que faz
        Retorna até `limit` execuções, da mais recente para a mais antiga.
        """
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        return self.connection.execute(
            """SELECT id, started_at, script_path, status, classification,
                      duration_ms
               FROM executions
               ORDER BY id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()

    def execution_exists(self, execution_id: int) -> bool:
        """Return whether the requested execution is present in the history."""
        row = self.connection.execute(
            "SELECT 1 FROM executions WHERE id = ?", (execution_id,)
        ).fetchone()
        return row is not None

    def list_logs(self, execution_id: int):
        """Return an execution's events in the order they were recorded."""
        return self.connection.execute(
            """SELECT recorded_at, elapsed_ms, level, event_type, message,
                      details_json
               FROM logs
               WHERE execution_id = ?
               ORDER BY id""",
            (execution_id,),
        ).fetchall()

    def delete_execution(self, execution_id: int) -> bool:
        """### O que faz
        Exclui uma execução encerrada e devolve se alguma linha foi removida.
        """
        cursor = self.connection.execute(
            "DELETE FROM executions WHERE id = ? AND status <> 'RUNNING'",
            (execution_id,),
        )
        self.connection.commit()
        return cursor.rowcount > 0
