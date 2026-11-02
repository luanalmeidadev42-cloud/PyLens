import tempfile

import pytest

from pylens.config.settings import Settings
from pylens.core.executor import _read_output, run_script
from pylens.database.connection import connect
from pylens.monitoring.monitor import ProcessSample


def _settings(tmp_path, **kwargs):
    values = {
        "timeout_seconds": 5,
        "memory_limit_bytes": 1024 * 1024 * 1024,
        "cpu_limit_percent": 10000.0,
        "database_path": tmp_path / "history.sqlite3",
    }
    values.update(kwargs)
    return Settings(**values)


def _script(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_run_script_captures_output_and_persists_completed_result(tmp_path):
    script = _script(
        tmp_path,
        "success.py",
        "import sys, time\nprint('argument=' + sys.argv[1])\ntime.sleep(0.15)\n",
    )

    result = run_script(
        str(script),
        ["hello"],
        settings=_settings(tmp_path),
        working_directory=str(tmp_path),
    )

    assert result.status == "COMPLETED"
    assert result.exit_code == 0
    assert "argument=hello" in result.stdout
    assert result.classification == "NORMAL"
    connection = connect(tmp_path / "history.sqlite3")
    row = connection.execute(
        "SELECT status, classification FROM executions WHERE id = ?",
        (result.execution_id,),
    ).fetchone()
    assert tuple(row) == ("COMPLETED", "NORMAL")
    connection.close()


def test_run_script_classifies_nonzero_exit_as_failed(tmp_path):
    script = _script(
        tmp_path,
        "failure.py",
        "import sys\nprint('failure details', file=sys.stderr)\nsys.exit(7)\n",
    )

    result = run_script(
        str(script), settings=_settings(tmp_path), working_directory=str(tmp_path)
    )

    assert result.status == "FAILED"
    assert result.exit_code == 7
    assert "failure details" in result.stderr
    assert result.classification == "CRITICAL"
    assert "failure details" in result.classification_reasons[0]


@pytest.mark.parametrize(
    ("mode", "expected_section"),
    [("detailed", "Function profile"), ("deep", "Line profile")],
)
def test_profile_modes_generate_expected_summaries(tmp_path, mode, expected_section):
    script = _script(
        tmp_path,
        "profile_target.py",
        "import time\ndef work():\n    time.sleep(0.25)\nwork()\n",
    )

    result = run_script(
        str(script),
        settings=_settings(tmp_path, mode=mode),
        working_directory=str(tmp_path),
    )

    assert result.status == "COMPLETED"
    assert result.profile_summary is not None
    assert "Function profile" in result.profile_summary
    assert expected_section in result.profile_summary
    if mode == "deep":
        assert "time.sleep(0.25)" in result.profile_summary


@pytest.mark.parametrize(
    ("metric", "limit", "expected_status"),
    [
        ("cpu_percent", 25.0, "CPU_LIMIT"),
        ("memory_rss_bytes", 1024, "MEMORY_LIMIT"),
    ],
)
def test_resource_limit_stops_child_and_keeps_deep_profile_incomplete(
    tmp_path, monkeypatch, metric, limit, expected_status
):
    script = _script(tmp_path, "waiting.py", "import time\ntime.sleep(10)\n")
    sample_values = {
        "cpu_percent": 50.0,
        "memory_rss_bytes": 2048,
        "memory_vms_bytes": 4096,
        "child_memory_rss_bytes": 0,
        "thread_count": 1,
        "process_count": 1,
        "process_tree_complete": True,
    }
    sample_values[metric] = limit + 1

    class FixedMonitor:
        def __init__(self, pid):
            self.pid = pid

        def sample(self):
            return ProcessSample(**sample_values)

    monkeypatch.setattr("pylens.core.executor.ProcessMonitor", FixedMonitor)
    settings_values = {
        "mode": "deep",
        "cpu_limit_percent": 25.0,
        "memory_limit_bytes": 1024 * 1024 * 1024,
    }
    if expected_status == "MEMORY_LIMIT":
        settings_values.update(cpu_limit_percent=10000.0, memory_limit_bytes=limit)

    result = run_script(
        str(script),
        settings=_settings(tmp_path, **settings_values),
        working_directory=str(tmp_path),
    )

    assert result.status == expected_status
    assert result.classification == "CRITICAL"
    assert result.profile_summary is None
    connection = connect(tmp_path / "history.sqlite3")
    event_types = [
        row[0]
        for row in connection.execute(
            "SELECT event_type FROM logs WHERE execution_id = ?",
            (result.execution_id,),
        )
    ]
    assert "PROFILE_INCOMPLETE" in event_types
    connection.close()


def test_timeout_stops_script_and_records_timeout_event(tmp_path, monkeypatch):
    script = _script(tmp_path, "slow.py", "import time\ntime.sleep(5)\n")

    class LowUsageMonitor:
        def __init__(self, pid):
            self.pid = pid

        def sample(self):
            return ProcessSample(0.0, 1024, 2048, 0, 1, 1, True)

    monkeypatch.setattr("pylens.core.executor.ProcessMonitor", LowUsageMonitor)
    result = run_script(
        str(script),
        settings=_settings(tmp_path, timeout_seconds=1),
        working_directory=str(tmp_path),
    )

    assert result.status == "TIMEOUT"
    assert result.classification == "CRITICAL"
    connection = connect(tmp_path / "history.sqlite3")
    assert connection.execute(
        "SELECT COUNT(*) FROM logs WHERE execution_id = ? AND event_type = 'TIMEOUT_REACHED'",
        (result.execution_id,),
    ).fetchone()[0] == 1
    connection.close()


def test_invalid_script_path_is_rejected_before_database_open(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_script(
            str(tmp_path / "missing.py"),
            settings=_settings(tmp_path),
        )


def test_read_output_keeps_only_the_last_mebibyte():
    with tempfile.TemporaryFile() as output_file:
        output_file.write(b"a" * (1024 * 1024 + 10))

        output = _read_output(output_file)

    assert output.startswith("[Earlier output omitted")
    assert len(output.splitlines()[-1]) == 1024 * 1024
