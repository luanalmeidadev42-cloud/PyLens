"""Coordinate function and line profiling for scripts monitored by PyLens."""

import argparse
from collections import defaultdict
import cProfile
from io import StringIO
import json
import linecache
import os
from pathlib import Path
import pstats
import sys
import threading
from threading import Lock
from time import perf_counter
from typing import Optional, Sequence


PROFILED_MODES = {"detailed", "deep"}


def _prepare_script(script_path: str):
    """Compile source with the globals and import path of a direct script run."""
    script_path = os.path.abspath(script_path)
    script_directory = os.path.dirname(script_path)
    sys.path.insert(0, script_directory)
    script_globals = {
        "__name__": "__main__",
        "__file__": script_path,
        "__package__": None,
        "__cached__": None,
        "__loader__": None,
        "__spec__": None,
        "__builtins__": __builtins__,
    }
    with open(script_path, "rb") as source_file:
        source = source_file.read()
    return compile(source, script_path, "exec"), script_globals


def build_profile_command(
    script_path: Path,
    arguments: Sequence[str],
    *,
    mode: str,
    function_output_path: str,
    line_output_path: Optional[str] = None,
) -> tuple[str, ...]:
    """Build the child-process command for the profiling mode selected."""
    if mode not in PROFILED_MODES:
        raise ValueError("profiling is available only in detailed and deep modes")
    if mode == "deep" and line_output_path is None:
        raise ValueError("deep mode requires a line-profile output path")

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--mode",
        mode,
        "--function-output",
        function_output_path,
    ]
    if line_output_path is not None:
        command.extend(("--line-output", line_output_path))
    command.extend(("--", str(script_path), *(str(arg) for arg in arguments)))
    return tuple(command)


def format_profile_summary(
    mode: str,
    function_output_path: str,
    line_output_path: Optional[str] = None,
) -> str:
    """Format the function summary and, for deep mode, the line summary."""
    output = []
    function_stats = pstats.Stats(function_output_path)
    function_stats.strip_dirs().sort_stats("cumulative")
    stream = StringIO()
    function_stats.stream = stream
    function_stats.print_stats(20)
    output.append("Function profile (top 20 by cumulative time):\n" + stream.getvalue())

    if mode == "deep":
        if line_output_path is None:
            raise ValueError("deep mode has no line-profile output path")
        with open(line_output_path, encoding="utf-8") as profile_file:
            line_stats = json.load(profile_file)
        entries = sorted(
            line_stats,
            key=lambda item: item["total_seconds"],
            reverse=True,
        )[:20]
        lines = ["Line profile (top 20 by total time):"]
        for item in entries:
            source = linecache.getline(item["filename"], item["line"]).strip()
            lines.append(
                f"{item['total_seconds']:.6f}s  {item['hits']} hits  "
                f"{item['filename']}:{item['line']}  {source}"
            )
        if not entries:
            lines.append("No target-script line timings were collected.")
        output.append("\n".join(lines))

    return "\n\n".join(output)


def _line_profile(script_path: str, output_path: str, code, script_globals) -> None:
    """Run the target with a line tracer and save target-file timings as JSON."""
    target_path = os.path.normcase(os.path.realpath(script_path))
    collected = defaultdict(lambda: {"hits": 0, "total_seconds": 0.0})
    active_lines = {}
    lock = Lock()
    is_active = True

    def finish_line(frame_id: int, now: float) -> None:
        previous = active_lines.pop(frame_id, None)
        if previous is None:
            return
        filename, line_number, started = previous
        collected[(filename, line_number)]["total_seconds"] += max(0.0, now - started)

    def local_trace(frame, event, arg):
        nonlocal is_active
        if not is_active:
            return None
        frame_id = id(frame)
        now = perf_counter()
        with lock:
            if event == "line":
                finish_line(frame_id, now)
                filename = os.path.normcase(os.path.realpath(frame.f_code.co_filename))
                line_number = frame.f_lineno
                collected[(filename, line_number)]["hits"] += 1
                active_lines[frame_id] = (filename, line_number, perf_counter())
            elif event == "return":
                finish_line(frame_id, now)
        return local_trace

    def global_trace(frame, event, arg):
        if event != "call":
            return None
        filename = os.path.normcase(os.path.realpath(frame.f_code.co_filename))
        return local_trace if filename == target_path else None

    previous_argv = sys.argv
    previous_trace = sys.gettrace()
    sys.argv = [script_path, *sys.argv[1:]]
    threading.settrace(global_trace)
    sys.settrace(global_trace)
    try:
        exec(code, script_globals, script_globals)
    finally:
        threading.settrace(None)
        sys.settrace(previous_trace)
        with lock:
            is_active = False
            now = perf_counter()
            for frame_id in tuple(active_lines):
                finish_line(frame_id, now)
        sys.argv = previous_argv
        result = [
            {
                "filename": filename,
                "line": line_number,
                "hits": values["hits"],
                "total_seconds": values["total_seconds"],
            }
            for (filename, line_number), values in collected.items()
        ]
        result.sort(key=lambda item: (item["filename"], item["line"]))
        with open(output_path, "w", encoding="utf-8") as profile_file:
            json.dump(result, profile_file)


def _run_target(
    mode: str,
    function_output_path: str,
    line_output_path: Optional[str],
    script_path: str,
    script_arguments: Sequence[str],
) -> None:
    """Execute a target script under the selected profiler."""
    sys.argv = [script_path, *script_arguments]
    code, script_globals = _prepare_script(script_path)
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        if mode == "deep":
            if line_output_path is None:
                raise ValueError("deep mode requires a line-profile output path")
            _line_profile(script_path, line_output_path, code, script_globals)
        else:
            exec(code, script_globals, script_globals)
    finally:
        profiler.disable()
        profiler.dump_stats(function_output_path)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run a target script as a profiling subprocess helper."""
    parser = argparse.ArgumentParser(prog="pylens-profiler")
    parser.add_argument("--mode", choices=sorted(PROFILED_MODES), required=True)
    parser.add_argument("--function-output", required=True)
    parser.add_argument("--line-output")
    parser.add_argument("script")
    parser.add_argument("script_arguments", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)
    if parsed.mode == "deep" and not parsed.line_output:
        parser.error("--line-output is required in deep mode")

    _run_target(
        parsed.mode,
        parsed.function_output,
        parsed.line_output,
        parsed.script,
        parsed.script_arguments,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
