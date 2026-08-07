"""Testes do loop ReAct (agent/loop.py) usando um LLMClient fake — cobre a
secão 8 do PLANO.md (exceto os itens que exigem o modelo real; ver tests/live/)
sem precisar de GPU nem de um servidor Ollama rodando.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from agent.config import AgentConfig
from agent.llm_client import AssistantMessage, ToolCallRequest
from agent.loop import MAX_ITERS_MSG, run_agent
from agent.tools import build_default_registry
from agent.tools.registry import ToolRegistry, ToolSpec


class FakeLLMClient:
    """Retorna as respostas passadas, em ordem, ignorando o conteúdo de messages/tools."""

    def __init__(self, responses: list[AssistantMessage]):
        self._responses = list(responses)
        self.chamadas = 0

    def chat(self, messages, tools) -> AssistantMessage:
        if self.chamadas >= len(self._responses):
            raise AssertionError("FakeLLMClient ficou sem respostas roteirizadas")
        resp = self._responses[self.chamadas]
        self.chamadas += 1
        return resp


def _call(id_: str, name: str, args: dict) -> ToolCallRequest:
    import json

    return ToolCallRequest(id=id_, name=name, args_raw=json.dumps(args), args=args)


@pytest.fixture
def config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(allowed_dirs=[tmp_path], max_iters=6, tool_timeout_s=1.0, task_timeout_s=5.0)


@pytest.fixture
def registry(config: AgentConfig) -> ToolRegistry:
    return build_default_registry(config)


def test_uma_tool_call_e_resposta_final(registry, config):
    client = FakeLLMClient(
        [
            AssistantMessage(
                content=None,
                tool_calls=[_call("1", "calcular", {"expressao": "2 + 2"})],
            ),
            AssistantMessage(content="O resultado é 4.", tool_calls=[]),
        ]
    )

    result = run_agent("quanto é 2 + 2?", registry=registry, client=client, config=config)

    assert result.status == "ok"
    assert result.content == "O resultado é 4."
    assert result.iterations == 2
    assert result.trace[0]["result"]["resultado"] == 4


def test_cadeia_curta_dois_passos(tmp_path: Path, registry, config):
    arquivo = tmp_path / "relatorio.txt"
    arquivo.write_text("conteúdo do relatório", encoding="utf-8")

    client = FakeLLMClient(
        [
            AssistantMessage(
                content=None,
                tool_calls=[_call("1", "buscar_arquivo", {"diretorio": str(tmp_path), "padrao": "*.txt"})],
            ),
            AssistantMessage(
                content=None,
                tool_calls=[_call("2", "ler_arquivo", {"caminho": str(arquivo)})],
            ),
            AssistantMessage(content="O relatório contém: conteúdo do relatório", tool_calls=[]),
        ]
    )

    result = run_agent("resuma o relatorio.txt", registry=registry, client=client, config=config)

    assert result.status == "ok"
    assert result.iterations == 3
    assert result.trace[0]["result"]["ok"] is True
    assert result.trace[1]["result"]["conteudo"] == "conteúdo do relatório"


def test_limite_de_iteracoes_falha_limpo(registry):
    config = AgentConfig(allowed_dirs=[Path.cwd()], max_iters=3, tool_timeout_s=1.0, task_timeout_s=10.0)
    # sempre chama a ferramenta com args distintos, nunca conclui
    respostas = [
        AssistantMessage(content=None, tool_calls=[_call(str(i), "calcular", {"expressao": f"{i} + 1"})])
        for i in range(10)
    ]
    client = FakeLLMClient(respostas)

    result = run_agent("tarefa sem fim", registry=registry, client=client, config=config)

    assert result.status == "failed"
    assert result.content == MAX_ITERS_MSG
    assert result.iterations == 3


def test_deteccao_de_loop_aborta_tarefa(registry, config):
    args = {"expressao": "1 + 1"}
    client = FakeLLMClient(
        [
            AssistantMessage(content=None, tool_calls=[_call("1", "calcular", args)]),
            AssistantMessage(content=None, tool_calls=[_call("2", "calcular", dict(args))]),
            AssistantMessage(content="não deveria chegar aqui", tool_calls=[]),
        ]
    )

    result = run_agent("repete a mesma chamada", registry=registry, client=client, config=config)

    assert result.status == "failed"
    assert "loop" in result.content.lower() or "abortando" in result.content.lower()
    assert client.chamadas == 2  # não chegou na 3a resposta


def test_ferramenta_nao_whitelistada_nao_derruba_o_loop(registry, config):
    client = FakeLLMClient(
        [
            AssistantMessage(content=None, tool_calls=[_call("1", "ferramenta_fantasma", {})]),
            AssistantMessage(content="essa ferramenta não existe, não posso ajudar.", tool_calls=[]),
        ]
    )

    result = run_agent("use uma ferramenta inexistente", registry=registry, client=client, config=config)

    assert result.status == "ok"
    assert result.trace[0]["result"]["ok"] is False


def test_argumentos_invalidos_sao_rejeitados_antes_de_executar(registry, config):
    client = FakeLLMClient(
        [
            AssistantMessage(content=None, tool_calls=[_call("1", "calcular", {"nao_existe": "x"})]),
            AssistantMessage(content="argumentos inválidos, não consegui calcular.", tool_calls=[]),
        ]
    )

    result = run_agent("chame calcular sem o campo certo", registry=registry, client=client, config=config)

    assert result.status == "ok"
    assert result.trace[0]["result"]["ok"] is False
    assert "inválid" in result.trace[0]["result"]["error"].lower()


def test_json_malformado_nao_derruba_o_loop(registry, config):
    quebrado = ToolCallRequest(id="1", name="calcular", args_raw="{not valid json", args=None)
    client = FakeLLMClient(
        [
            AssistantMessage(content=None, tool_calls=[quebrado]),
            AssistantMessage(content="tentei de novo com json válido.", tool_calls=[]),
        ]
    )

    result = run_agent("json quebrado", registry=registry, client=client, config=config)

    assert result.status == "ok"
    assert result.trace[0]["result"]["ok"] is False


def test_timeout_de_ferramenta_e_capturado(config):
    def lenta(**_kwargs):
        time.sleep(0.3)
        return {"ok": True}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="lenta",
            description="ferramenta de teste que demora",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lenta,
        )
    )
    config_rapido = AgentConfig(
        allowed_dirs=config.allowed_dirs, max_iters=6, tool_timeout_s=0.05, task_timeout_s=5.0
    )
    client = FakeLLMClient(
        [
            AssistantMessage(content=None, tool_calls=[_call("1", "lenta", {})]),
            AssistantMessage(content="deu timeout, parei.", tool_calls=[]),
        ]
    )

    result = run_agent("chame a ferramenta lenta", registry=registry, client=client, config=config_rapido)

    assert result.status == "ok"
    assert result.trace[0]["result"]["ok"] is False
    assert "timeout" in result.trace[0]["result"]["error"].lower()
