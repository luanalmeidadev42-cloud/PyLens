"""Classify completed executions from their outcome and resource measurements."""

from dataclasses import dataclass
import math
from typing import Optional, Tuple


WARNING_BUDGET_RATIO = 0.8


@dataclass(frozen=True)
class ClassificationResult:
    """A severity label and the factors that produced it."""

    classification: str
    reasons: Tuple[str, ...]


def classify_execution(
    *,
    status: str,
    duration_seconds: float,
    timeout_seconds: int,
    peak_cpu_percent: Optional[float],
    cpu_limit_percent: float,
    peak_memory_bytes: Optional[int],
    memory_limit_bytes: int,
    sample_count: int,
    monitoring_complete: bool,
    exit_code: Optional[int],
    error_summary: Optional[str] = None,
    stderr_output: str = "",
) -> ClassificationResult:
    """Classify the outcome, runtime, resource use, and measurement quality.

    A warning is raised at 80% of a configured time or resource budget. These
    are advisory thresholds; the configured limits themselves remain the
    executor's enforcement thresholds.
    """
    if status in {"FAILED", "INTERNAL_ERROR", "TIMEOUT", "MEMORY_LIMIT", "CPU_LIMIT"}:
        reason = {
            "FAILED": "The target script exited with an error.",
            "INTERNAL_ERROR": "PyLens encountered an internal error.",
            "TIMEOUT": "The execution reached its timeout limit.",
            "MEMORY_LIMIT": "The process tree reached its memory limit.",
            "CPU_LIMIT": "The process tree reached its CPU limit.",
        }[status]
        if error_summary:
            reason = f"{reason} {error_summary}"
        return ClassificationResult("CRITICAL", (reason,))

    if status == "INTERRUPTED":
        return ClassificationResult("WARNING", ("The execution was interrupted by the user.",))

    if status != "COMPLETED":
        return ClassificationResult(
            "UNDETERMINED", (f"Execution status '{status}' has no classification rule.",)
        )

    if exit_code is None:
        return ClassificationResult("UNDETERMINED", ("The process exit code is unavailable.",))
    if exit_code != 0:
        return ClassificationResult(
            "CRITICAL", (f"The target script exited with code {exit_code}.",)
        )
    if sample_count <= 0 and not stderr_output.strip():
        return ClassificationResult(
            "UNDETERMINED", ("No resource samples were collected for this execution.",)
        )

    reasons = []
    if stderr_output.strip():
        reasons.append("The script wrote output to standard error despite exiting successfully.")
    if sample_count <= 0:
        reasons.append("No resource samples were collected for this execution.")
    if not monitoring_complete:
        reasons.append("At least one process-tree resource sample was incomplete.")

    if peak_cpu_percent is None or not math.isfinite(peak_cpu_percent):
        reasons.append("CPU usage could not be measured reliably.")
    elif peak_cpu_percent >= cpu_limit_percent * WARNING_BUDGET_RATIO:
        reasons.append(
            f"Peak CPU use ({peak_cpu_percent:.1f}%) reached at least 80% of its configured limit."
        )

    if peak_memory_bytes is None:
        reasons.append("Memory use could not be measured reliably.")
    elif peak_memory_bytes >= memory_limit_bytes * WARNING_BUDGET_RATIO:
        memory_mib = peak_memory_bytes / (1024 * 1024)
        limit_mib = memory_limit_bytes / (1024 * 1024)
        reasons.append(
            f"Peak memory use ({memory_mib:.1f} MiB) reached at least 80% of its configured limit ({limit_mib:.1f} MiB)."
        )

    if duration_seconds >= timeout_seconds * WARNING_BUDGET_RATIO:
        reasons.append(
            f"Runtime ({duration_seconds:.1f}s) reached at least 80% of the configured timeout."
        )

    if reasons:
        return ClassificationResult("WARNING", tuple(reasons))
    return ClassificationResult(
        "NORMAL", ("The script completed successfully within its resource budgets.",)
    )
