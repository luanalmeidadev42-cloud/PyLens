import json

from pylens.database.connection import connect
from pylens.database.repository import ExecutionRepository, utc_now
from pylens.interface.cli import main


def _completed_execution(database_path):
    connection = connect(database_path)
    repository = ExecutionRepository(connection)
    execution_id = repository.create_execution(
        script_path="/tmp/example.py",
        arguments=[],
        mode="normal",
        started_at=utc_now(),
        timeout_seconds=10,
        memory_limit_bytes=1024 * 1024,
        configuration={},
    )
    repository.add_log(
        execution_id,
        level="WARNING",
        event_type="SAMPLE_EVENT",
        message="A message",
        details={"measurement": 12},
        elapsed_ms=12,
    )
    repository.finish_execution(
        execution_id,
        finished_at=utc_now(),
        duration_ms=12,
        status="COMPLETED",
        classification="NORMAL",
        exit_code=0,
    )
    connection.close()
    return execution_id


def test_history_lists_saved_execution(tmp_path, capsys):
    database_path = tmp_path / "history.sqlite3"
    execution_id = _completed_execution(database_path)

    result = main(["history", "--database", str(database_path)])

    captured = capsys.readouterr()
    assert result == 0
    assert str(execution_id) in captured.out
    assert "COMPLETED" in captured.out


def test_logs_support_lite_normal_and_deep_detail(tmp_path, capsys):
    database_path = tmp_path / "history.sqlite3"
    execution_id = _completed_execution(database_path)

    assert main(["logs", str(execution_id), "--detail", "lite", "--database", str(database_path)]) == 0
    assert "SAMPLE_EVENT" in capsys.readouterr().out

    assert main(["logs", str(execution_id), "--detail", "normal", "--database", str(database_path)]) == 0
    normal_output = capsys.readouterr().out
    assert "WARNING" in normal_output
    assert "A message" in normal_output

    assert main(["logs", str(execution_id), "--detail", "deep", "--database", str(database_path)]) == 0
    deep_output = capsys.readouterr().out
    assert json.dumps({"measurement": 12}, indent=2, ensure_ascii=False, sort_keys=True) in deep_output


def test_logs_reports_missing_execution(tmp_path, capsys):
    result = main(["logs", "999", "--database", str(tmp_path / "history.sqlite3")])

    assert result == 1
    assert "was not found" in capsys.readouterr().err


def test_delete_removes_saved_execution_and_related_data(tmp_path, capsys):
    database_path = tmp_path / "history.sqlite3"
    execution_id = _completed_execution(database_path)

    result = main(["delete", str(execution_id), "--yes", "--database", str(database_path)])

    assert result == 0
    assert "Deleted execution" in capsys.readouterr().out
