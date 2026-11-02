"""Default settings and validation for PyLens executions."""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Optional


DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_CPU_LIMIT_PERCENT = 100.0
MODE_INTERVAL_SECONDS = {
    "normal": 1.0,
    "detailed": 0.1,
    "deep": 0.1,
}


@dataclass(frozen=True)
class Settings:
    mode: str = "normal"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES
    database_path: Optional[Path] = None
    cpu_limit_percent: float = DEFAULT_CPU_LIMIT_PERCENT

    def __post_init__(self) -> None:
        """### O que faz
        Valida modo, timeout e limite de memória ao construir as configurações.
        """
        if self.mode not in MODE_INTERVAL_SECONDS:
            raise ValueError("mode must be normal, detailed, or deep")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if self.memory_limit_bytes <= 0:
            raise ValueError("memory_limit_bytes must be greater than zero")
        if not math.isfinite(self.cpu_limit_percent) or self.cpu_limit_percent <= 0:
            raise ValueError("cpu_limit_percent must be a finite number greater than zero")

    @property
    def sample_interval_seconds(self) -> float:
        """### O que faz
        Devolve o intervalo de amostragem associado ao modo selecionado.
        """
        return MODE_INTERVAL_SECONDS[self.mode]

    @property
    def effective_database_path(self) -> Path:
        """### O que faz
        Devolve o caminho expandido informado ou o caminho padrão do histórico.
        """
        if self.database_path is not None:
            return self.database_path.expanduser()
        return Path.home() / ".pylens" / "history.sqlite3"
