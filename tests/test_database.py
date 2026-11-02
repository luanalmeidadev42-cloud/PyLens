import json
import sqlite3
from pathlib import Path

from pylens.database.connection import connect
from pylens.database.repository import ExecutionRepository, utc_now


def _create_execution(repository, **overrides):
    values = {
        "script_path": "/tmp/sample.py",
        "arguments": ["--value", "1"],
        "mode": "normal",
        "started_at": utc_now(),
        "timeout_seconds": 30,
        "memory_limit_bytes": 1024 * 1024 * 1024,
        "configuration": {"cpu_limit_percent": 100.0},
    }
    values.update(overrides)
    return repository.create_execution(**values)


def test_repository_records_runs_samples_and_events_then_deletes_cascade(tmp_path):
    connection = connect(tmp_path / "history.sqlite3")
    repository = ExecutionRepository(connection)
    execution_id = _create_execution(repository)
    repository.add_sample(
        execution_id,
        collected_at=utc_now(),
        elapsed_ms=25,
        cpu_percent=12.5,
        memory_rss_bytes=4096,
        memory_vms_bytes=8192,
        child_memory_rss_bytes=0,
        thread_count=1,
        process_count=1,
    )
    repository.add_log(
        execution_id,
        level="INFO",
        event_type="TEST_EVENT",
        message="sample event",
        details={"answer": 42},
        elapsed_ms=25,
    )
    repository.finish_execution(
        execution_id,
        finished_at=utc_now(),
        duration_ms=25,
        status="COMPLETED",
        classification="NORMAL",
        exit_code=0,
    )

    rows = repository.list_executions()
    logs = repository.list_logs(execution_id)
    assert rows[0]["id"] == execution_id
    assert repository.execution_exists(execution_id)
    assert logs[0]["event_type"] == "TEST_EVENT"
    assert json.loads(logs[0]["details_json"]) == {"answer": 42}
    assert not repository.delete_execution(execution_id + 100)
    assert repository.delete_execution(execution_id)
    assert connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM logs").fetchone()[0] == 0
    connection.close()


def test_running_execution_cannot_be_deleted(tmp_path):
    connection = connect(tmp_path / "history.sqlite3")
    repository = ExecutionRepository(connection)
    execution_id = _create_execution(repository)

    assert not repository.delete_execution(execution_id)
    assert repository.execution_exists(execution_id)
    connection.close()


def test_existing_database_migrates_cpu_limit_status(tmp_path):
    database_path = tmp_path / "old-history.sqlite3"
    schema_path = Path(__file__).parents[1] / "src" / "pylens" / "database" / "database.sql"
    old_schema = schema_path.read_text(encoding="utf-8").replace("            'CPU_LIMIT',\n", "")
    old_connection = sqlite3.connect(database_path)
    old_connection.executescript(old_schema)
    old_connection.close()

    connection = connect(database_path)
    repository = ExecutionRepository(connection)
    execution_id = _create_execution(repository)
    repository.finish_execution(
        execution_id,
        finished_at=utc_now(),
        duration_ms=100,
        status="CPU_LIMIT",
        classification="CRITICAL",
        exit_code=None,
    )

    assert connection.execute(
        "SELECT status FROM executions WHERE id = ?", (execution_id,)
    ).fetchone()["status"] == "CPU_LIMIT"
    connection.close()
