# PyLens

PyLens runs Python scripts in a separate process, samples resource usage, and stores a local execution history in SQLite.

## Install for development

```bash
python -m pip install -e .
```

## Aprenda como o código funciona

O guia [Explicação do código](docs/EXPLICACAO_DO_CODIGO.md) apresenta o fluxo do PyLens, explica os principais conceitos e descreve o papel de cada módulo do projeto.

A [Referência de sintaxes](docs/REFERENCIA_SINTAXES.md) explica os comandos da CLI, suas opções, os modos de execução, as estruturas Python e o esquema SQL usados pelo projeto.

## Run a script

```bash
pylens run path/to/script.py
```

For a guided menu that asks for the script and settings instead of requiring command-line options, run:

```bash
pylens-menu
```

From a source checkout, run `PYTHONPATH=src python3 -m pylens.interface`. The menu provides the same run, history, logs, and delete actions as the command-line interface.

Pass PyLens options before `--` and arguments for the target script after it:

```bash
pylens run path/to/script.py --mode detailed --timeout 120 --memory-limit-mib 2048 --cpu-limit-percent 100 -- --input data.csv
```

The initial defaults are a 120 second timeout, a sampled 2048 MiB process-tree memory limit, a sampled 100% process-tree CPU limit, and one second between normal-mode samples. CPU and memory limits are checked between samples, so a process can exceed them briefly before it is stopped; these limits are not an operating-system sandbox. The `detailed` mode samples every 100 ms and reports function costs with `cProfile`. The `deep` mode also profiles target-script lines using Python tracing; line profiling adds noticeable overhead and reports inclusive wall time for each line.

The SQLite database is created at `~/.pylens/history.sqlite3` by default. Use `--database` to choose another local path. Each execution is recorded before the target starts, and resource samples and events are committed incrementally.

View recent runs, inspect their event logs, and delete a completed run with:

```bash
pylens history
pylens logs 3 --detail normal
pylens logs 3 --detail deep
pylens delete 3
```

Deletion also removes that execution's samples and logs. The delete command asks for confirmation; pass `--yes` to skip the prompt.

Script arguments are stored in that local history to describe the execution. Avoid passing secrets as command-line arguments; the database is local, but its contents are not redacted or encrypted by PyLens.

## Current limits

- Profiling and process metrics can affect the measured execution.
- CPU percentage is a sampled process-tree measurement and may exceed 100% on multi-core systems.
- Detailed profiling summarizes Python functions. Native extension internals, such as work inside NumPy, are not decomposed by `cProfile`.
- Deep line profiling times lines in the target script; time spent inside a function called from a line is included in that line's wall time.
- A separate process is not a security sandbox. The target runs with the current user's permissions.
- Standard output and standard error are retained only up to their last 1 MiB in the terminal result.
