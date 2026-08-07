"""Fixtures dos testes 'live' (secão 8 do PLANO.md): exigem um Ollama real
rodando com o modelo carregado. Auto-skip se o servidor não estiver de pé.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from agent.config import AgentConfig
from agent.llm_client import OllamaLLMClient
from agent.tools import build_default_registry


def _ollama_up(base_url: str) -> bool:
    tags_url = base_url.rstrip("/").removesuffix("/v1") + "/api/tags"
    try:
        with urllib.request.urlopen(tags_url, timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


@pytest.fixture(scope="session")
def live_config(tmp_path_factory) -> AgentConfig:
    base = AgentConfig()
    if not _ollama_up(base.ollama_base_url):
        pytest.skip(f"Servidor Ollama não está acessível em {base.ollama_base_url}")
    workdir = tmp_path_factory.mktemp("live_agent_sandbox")
    return AgentConfig(
        ollama_base_url=base.ollama_base_url,
        model=base.model,
        allowed_dirs=[workdir],
        max_iters=6,
        tool_timeout_s=20.0,
        task_timeout_s=180.0,
        temperature=base.temperature,
        top_p=base.top_p,
    )


@pytest.fixture(scope="session")
def live_client(live_config: AgentConfig) -> OllamaLLMClient:
    return OllamaLLMClient(live_config)


@pytest.fixture(scope="session")
def live_registry(live_config: AgentConfig):
    return build_default_registry(live_config)
