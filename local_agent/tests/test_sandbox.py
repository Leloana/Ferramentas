from pathlib import Path

import pytest

from agent.sandbox import SandboxViolation, resolve_within_sandbox


def test_caminho_absoluto_dentro_do_sandbox_eh_permitido(tmp_path: Path):
    allowed = [tmp_path]
    alvo = tmp_path / "sub" / "arquivo.txt"
    alvo.parent.mkdir()
    alvo.write_text("ok")

    resolved = resolve_within_sandbox(str(alvo), allowed)

    assert resolved == alvo.resolve()


def test_caminho_relativo_resolve_a_partir_do_primeiro_dir_permitido(tmp_path: Path):
    allowed = [tmp_path]
    resolved = resolve_within_sandbox("arquivo.txt", allowed)
    assert resolved.parent == tmp_path.resolve()


def test_path_traversal_eh_bloqueado(tmp_path: Path):
    allowed_sub = tmp_path / "sandbox"
    allowed_sub.mkdir()
    fora = tmp_path / "fora.txt"
    fora.write_text("segredo")

    with pytest.raises(SandboxViolation):
        resolve_within_sandbox(str(allowed_sub / ".." / "fora.txt"), [allowed_sub])


def test_caminho_absoluto_fora_do_sandbox_eh_bloqueado(tmp_path: Path):
    allowed = [tmp_path / "sandbox"]
    outro = tmp_path / "outro_dir" / "arquivo.txt"

    with pytest.raises(SandboxViolation):
        resolve_within_sandbox(str(outro), allowed)


def test_sem_diretorios_permitidos_bloqueia_tudo():
    with pytest.raises(SandboxViolation):
        resolve_within_sandbox("qualquer coisa", [])
