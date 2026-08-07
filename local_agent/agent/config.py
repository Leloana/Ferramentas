"""Configuração do agente local, lida de variáveis de ambiente (com defaults seguros)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_dirs(name: str, default: list[str]) -> list[Path]:
    raw = os.environ.get(name)
    if not raw:
        return [Path(d).expanduser().resolve() for d in default]
    parts = [p for p in raw.split(os.pathsep) if p.strip()]
    return [Path(p).expanduser().resolve() for p in parts]


@dataclass(frozen=True)
class AgentConfig:
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "LOCAL_AGENT_OLLAMA_BASE_URL", "http://localhost:11434/v1"
        )
    )
    model: str = field(
        default_factory=lambda: os.environ.get(
            "LOCAL_AGENT_MODEL", "qwen3.5:9b-instruct"
        )
    )
    max_iters: int = field(default_factory=lambda: _env_int("LOCAL_AGENT_MAX_ITERS", 6))
    tool_timeout_s: float = field(
        default_factory=lambda: _env_float("LOCAL_AGENT_TOOL_TIMEOUT", 15.0)
    )
    task_timeout_s: float = field(
        default_factory=lambda: _env_float("LOCAL_AGENT_TASK_TIMEOUT", 90.0)
    )
    temperature: float = field(
        default_factory=lambda: _env_float("LOCAL_AGENT_TEMPERATURE", 0.3)
    )
    top_p: float = field(default_factory=lambda: _env_float("LOCAL_AGENT_TOP_P", 0.9))
    allowed_dirs: list[Path] = field(
        default_factory=lambda: _env_dirs("LOCAL_AGENT_ALLOWED_DIRS", [str(Path.home())])
    )


DEFAULT_CONFIG = AgentConfig()
