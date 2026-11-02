import pytest

from pylens.core.classifier import classify_execution


def _classify(**overrides):
    values = {
        "status": "COMPLETED",
        "duration_seconds": 2.0,
        "timeout_seconds": 10,
        "peak_cpu_percent": 30.0,
        "cpu_limit_percent": 100.0,
        "peak_memory_bytes": 100 * 1024 * 1024,
        "memory_limit_bytes": 1024 * 1024 * 1024,
        "sample_count": 3,
        "monitoring_complete": True,
        "exit_code": 0,
    }
    values.update(overrides)
    return classify_execution(**values)


@pytest.mark.parametrize(
    "status", ["FAILED", "INTERNAL_ERROR", "TIMEOUT", "MEMORY_LIMIT", "CPU_LIMIT"]
)
def test_execution_failures_are_critical(status):
    result = _classify(status=status, error_summary="test error")

    assert result.classification == "CRITICAL"
    assert result.reasons


def test_completed_execution_with_low_usage_is_normal():
    result = _classify()

    assert result.classification == "NORMAL"


@pytest.mark.parametrize(
    "values",
    [
        {"duration_seconds": 8.0},
        {"peak_cpu_percent": 80.0},
        {"peak_memory_bytes": 820 * 1024 * 1024},
        {"monitoring_complete": False},
        {"stderr_output": "a warning from the script"},
    ],
)
def test_resource_or_diagnostic_signals_raise_warning(values):
    result = _classify(**values)

    assert result.classification == "WARNING"
    assert result.reasons


def test_interrupted_execution_is_a_warning():
    assert _classify(status="INTERRUPTED").classification == "WARNING"


@pytest.mark.parametrize(
    "values",
    [
        {"sample_count": 0},
        {"exit_code": None},
        {"status": "UNKNOWN"},
    ],
)
def test_missing_or_unknown_result_is_undetermined(values):
    assert _classify(**values).classification == "UNDETERMINED"


def test_nonzero_exit_code_is_critical_even_if_status_says_completed():
    assert _classify(exit_code=3).classification == "CRITICAL"
