"""SQLite connection setup for the local execution history."""

import sqlite3
from pathlib import Path


def connect(database_path: Path) -> sqlite3.Connection:
    """### O que faz
    Abre o SQLite, habilita suas opções necessárias e aplica o esquema do PyLens.
    """
    database_path = database_path.expanduser()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA journal_mode = WAL")

    _migrate_cpu_limit_status(connection)

    connection.execute("PRAGMA foreign_keys = ON")

    schema_path = Path(__file__).with_name("database.sql")
    connection.executescript(schema_path.read_text(encoding="utf-8"))
    return connection


def _migrate_cpu_limit_status(connection: sqlite3.Connection) -> None:
    """Add CPU_LIMIT to the status constraint in databases created by older PyLens versions."""
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'executions'"
    ).fetchone()
    if row is None or "'CPU_LIMIT'" in row[0]:
        return

    connection.executescript(
        """
        BEGIN;
        CREATE TABLE executions_new (
            id INTEGER PRIMARY KEY,
            script_path TEXT NOT NULL,
            arguments_json TEXT NOT NULL DEFAULT '[]',
            mode TEXT NOT NULL CHECK (mode IN ('normal', 'detailed', 'deep')),
            pid INTEGER,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_ms INTEGER,
            status TEXT NOT NULL CHECK (status IN (
                'RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT', 'MEMORY_LIMIT',
                'CPU_LIMIT', 'INTERRUPTED', 'INTERNAL_ERROR'
            )),
            classification TEXT NOT NULL DEFAULT 'UNDETERMINED'
                CHECK (classification IN ('NORMAL', 'WARNING', 'CRITICAL', 'UNDETERMINED')),
            exit_code INTEGER,
            timeout_seconds INTEGER NOT NULL DEFAULT 120 CHECK (timeout_seconds > 0),
            memory_limit_bytes INTEGER NOT NULL CHECK (memory_limit_bytes > 0),
            configuration_json TEXT NOT NULL DEFAULT '{}',
            error_summary TEXT,
            CHECK (duration_ms IS NULL OR duration_ms >= 0),
            CHECK (finished_at IS NULL OR finished_at >= started_at)
        );
        INSERT INTO executions_new SELECT * FROM executions;
        DROP TABLE executions;
        ALTER TABLE executions_new RENAME TO executions;
        COMMIT;
        """
    )
