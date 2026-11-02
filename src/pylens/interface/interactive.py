"""Guided terminal menu that uses the same handlers as the command-line CLI."""

import math
import shlex
from typing import Optional, Sequence

from pylens.config.settings import (
    DEFAULT_CPU_LIMIT_PERCENT,
    DEFAULT_MEMORY_LIMIT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
)
from pylens.interface.cli import main as command_line_main


DEFAULT_MEMORY_LIMIT_MIB = DEFAULT_MEMORY_LIMIT_BYTES // (1024 * 1024)


def _read(prompt: str, default: Optional[str] = None) -> Optional[str]:
    suffix = f" [{default}]" if default is not None else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if default is not None:
        return answer or default
    return answer


def _positive_integer(prompt: str, default: int) -> Optional[int]:
    while True:
        answer = _read(prompt, str(default))
        if answer is None:
            return None
        try:
            value = int(answer)
        except ValueError:
            print("Digite um número inteiro maior que zero.")
            continue
        if value > 0:
            return value
        print("Digite um número inteiro maior que zero.")


def _positive_float(prompt: str, default: float) -> Optional[float]:
    while True:
        answer = _read(prompt, f"{default:g}")
        if answer is None:
            return None
        try:
            value = float(answer)
        except ValueError:
            print("Digite um número maior que zero.")
            continue
        if math.isfinite(value) and value > 0:
            return value
        print("Digite um número finito maior que zero.")


def _database_option(database: Optional[str]) -> list[str]:
    return ["--database", database] if database else []


def _run_script() -> Optional[list[str]]:
    script = _read("Caminho do script")
    if script is None:
        return None
    if not script:
        print("Informe o caminho do script.")
        return []

    mode = _read("Modo: normal, detailed ou deep", "normal")
    if mode is None:
        return None
    while mode not in ("normal", "detailed", "deep"):
        print("Escolha normal, detailed ou deep.")
        mode = _read("Modo", "normal")
        if mode is None:
            return None

    timeout = _positive_integer("Tempo limite em segundos", DEFAULT_TIMEOUT_SECONDS)
    if timeout is None:
        return None
    memory_limit = _positive_integer(
        "Limite de memória em MiB", DEFAULT_MEMORY_LIMIT_MIB
    )
    if memory_limit is None:
        return None
    cpu_limit = _positive_float("Limite de CPU em porcentagem", DEFAULT_CPU_LIMIT_PERCENT)
    if cpu_limit is None:
        return None

    workdir = _read("Diretório de trabalho (vazio para usar o diretório atual)")
    if workdir is None:
        return None
    database = _read("Arquivo do histórico (vazio para usar o padrão)")
    if database is None:
        return None
    script_arguments = _read("Argumentos do script, separados por espaços")
    if script_arguments is None:
        return None
    try:
        parsed_script_arguments = shlex.split(script_arguments)
    except ValueError as error:
        print(f"Não foi possível interpretar os argumentos do script: {error}")
        return []

    arguments = [
        "run",
        script,
        "--mode",
        mode,
        "--timeout",
        str(timeout),
        "--memory-limit-mib",
        str(memory_limit),
        "--cpu-limit-percent",
        str(cpu_limit),
    ]
    if workdir:
        arguments.extend(("--workdir", workdir))
    arguments.extend(_database_option(database))
    if parsed_script_arguments:
        arguments.extend(("--", *parsed_script_arguments))
    return arguments


def _history() -> Optional[list[str]]:
    limit = _positive_integer("Quantidade de execuções para mostrar", 20)
    if limit is None:
        return None
    database = _read("Arquivo do histórico (vazio para usar o padrão)")
    if database is None:
        return None
    return ["history", "--limit", str(limit), *_database_option(database)]


def _logs() -> Optional[list[str]]:
    execution_id = _positive_integer("ID da execução", 1)
    if execution_id is None:
        return None
    detail = _read("Detalhe dos logs: lite, normal ou deep", "normal")
    if detail is None:
        return None
    while detail not in ("lite", "normal", "deep"):
        print("Escolha lite, normal ou deep.")
        detail = _read("Detalhe dos logs", "normal")
        if detail is None:
            return None
    database = _read("Arquivo do histórico (vazio para usar o padrão)")
    if database is None:
        return None
    return [
        "logs",
        str(execution_id),
        "--detail",
        detail,
        *_database_option(database),
    ]


def _delete() -> Optional[list[str]]:
    execution_id = _positive_integer("ID da execução para excluir", 1)
    if execution_id is None:
        return None
    database = _read("Arquivo do histórico (vazio para usar o padrão)")
    if database is None:
        return None
    return ["delete", str(execution_id), *_database_option(database)]


def _dispatch(arguments: Sequence[str]) -> int:
    try:
        return command_line_main(arguments)
    except SystemExit as error:
        return int(error.code or 0)


def main() -> int:
    """Run the guided CLI menu until the user chooses to exit."""
    actions = {
        "1": ("Executar script", _run_script),
        "2": ("Ver histórico de execuções", _history),
        "3": ("Ver logs de uma execução", _logs),
        "4": ("Excluir uma execução", _delete),
    }
    while True:
        print(
            "\nMenu do PyLens\n"
            "  1. Executar script\n"
            "  2. Ver histórico de execuções\n"
            "  3. Ver logs de uma execução\n"
            "  4. Excluir uma execução\n"
            "  0. Sair"
        )
        choice = _read("Escolha uma opção")
        if choice is None or choice == "0":
            return 0
        action = actions.get(choice)
        if action is None:
            print("Escolha uma das opções listadas.")
            continue

        print(f"\n{action[0]}")
        arguments = action[1]()
        if arguments:
            _dispatch(arguments)
