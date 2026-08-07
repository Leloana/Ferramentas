from pathlib import Path

import pytest

from agent.config import AgentConfig
from agent.sandbox import SandboxViolation
from agent.tools import buscar_arquivo, calcular, data_hora, ler_arquivo, listar_diretorio


@pytest.fixture
def config(tmp_path: Path) -> AgentConfig:
    return AgentConfig(allowed_dirs=[tmp_path])


def test_buscar_arquivo_encontra_por_padrao(tmp_path: Path, config: AgentConfig):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.py").write_text("z")

    handler = buscar_arquivo.make_handler(config)
    result = handler(diretorio=str(tmp_path), padrao="*.py")

    assert result["ok"] is True
    assert result["total_encontrado"] == 2
    assert any("a.py" in f for f in result["arquivos"])
    assert any("c.py" in f for f in result["arquivos"])


def test_buscar_arquivo_fora_do_sandbox_levanta(tmp_path: Path, config: AgentConfig):
    handler = buscar_arquivo.make_handler(config)
    with pytest.raises(SandboxViolation):
        handler(diretorio=str(tmp_path.parent), padrao="*.py")


def test_ler_arquivo_conteudo_e_truncamento(tmp_path: Path, config: AgentConfig):
    alvo = tmp_path / "notas.txt"
    alvo.write_text("0123456789")

    handler = ler_arquivo.make_handler(config)
    result = handler(caminho=str(alvo), max_chars=4)

    assert result["ok"] is True
    assert result["conteudo"] == "0123"
    assert result["truncado"] is True


def test_ler_arquivo_inexistente(tmp_path: Path, config: AgentConfig):
    handler = ler_arquivo.make_handler(config)
    result = handler(caminho=str(tmp_path / "nao_existe.txt"))
    assert result["ok"] is False


def test_listar_diretorio(tmp_path: Path, config: AgentConfig):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "subdir").mkdir()

    handler = listar_diretorio.make_handler(config)
    result = handler(caminho=str(tmp_path))

    nomes = {e["nome"] for e in result["entradas"]}
    assert nomes == {"a.txt", "subdir"}


@pytest.mark.parametrize(
    "expressao, esperado",
    [
        ("2 + 2", 4),
        ("(3 + 4) * 2", 14),
        ("10 / 4", 2.5),
        ("2 ** 10", 1024),
        ("-5 + 3", -2),
    ],
)
def test_calcular_expressoes_validas(config: AgentConfig, expressao, esperado):
    handler = calcular.make_handler(config)
    result = handler(expressao=expressao)
    assert result["ok"] is True
    assert result["resultado"] == esperado


def test_calcular_bloqueia_codigo_arbitrario(config: AgentConfig):
    handler = calcular.make_handler(config)
    result = handler(expressao="__import__('os').system('echo hackeado')")
    assert result["ok"] is False


def test_calcular_divisao_por_zero(config: AgentConfig):
    handler = calcular.make_handler(config)
    result = handler(expressao="1 / 0")
    assert result["ok"] is False


def test_data_hora_atual_formato(config: AgentConfig):
    handler = data_hora.make_handler(config)
    result = handler()
    assert result["ok"] is True
    assert "T" in result["iso"]
