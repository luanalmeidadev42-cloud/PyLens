from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from pylens.config.settings import Settings
from pylens.core.executor import RunResult


def test_settings_defaults_and_mode_intervals(tmp_path):
    settings = Settings(database_path=tmp_path / "history.sqlite3")

    assert settings.mode == "normal"
    assert settings.timeout_seconds == 120
    assert settings.sample_interval_seconds == 1.0
    assert settings.effective_database_path == tmp_path / "history.sqlite3"
    assert Settings(mode="detailed").sample_interval_seconds == 0.1
    assert Settings(mode="deep").sample_interval_seconds == 0.1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "fast"},
        {"timeout_seconds": 0},
        {"memory_limit_bytes": 0},
        {"cpu_limit_percent": 0},
        {"cpu_limit_percent": float("nan")},
        {"cpu_limit_percent": float("inf")},
    ],
)
def test_settings_reject_invalid_values(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_default_database_path_is_under_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert Settings().effective_database_path == tmp_path / ".pylens" / "history.sqlite3"


def test_run_result_is_immutable():
    result = RunResult(
        execution_id=1,
        status="COMPLETED",
        classification="NORMAL",
        exit_code=0,
        duration_seconds=0.1,
        stdout="",
        stderr="",
    )

    with pytest.raises(FrozenInstanceError):
        result.status = "FAILED"
