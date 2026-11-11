"""Arranjo de piano com o AMT-APC (310hz/amt-apc, 2024): IA que gera "piano cover" a partir da música,
com 3 estilos que casam com os níveis: level1 = fácil, level2 = médio, level3 = difícil.

Instalação (fora do git, em modelos/):
  git clone https://github.com/310hz/amt-apc modelos/amt-apc
  curl -L -o modelos/amt-apc/models/params/apc.pth https://github.com/310hz/amt-apc/releases/download/beta/apc.pth
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = AQUI / "modelos" / "amt-apc"
ESTILO = {"facil": "level1", "medio": "level2", "dificil": "level3"}


# o checkpoint do AMT-APC foi salvo com os pesos na GPU: sem placa, torch.load falha. Este
# lançador roda o `infer` do repositório mapeando os pesos pra CPU quando não há CUDA (modo leve)
_RODAR_SEM_GPU = "\n".join([
    "import sys, runpy, torch",
    "if not torch.cuda.is_available() or torch.cuda.device_count() == 0:",
    "    _carregar = torch.load",
    "    torch.load = lambda *a, **k: _carregar(*a, **{**k, 'map_location': 'cpu'})",
    "sys.argv = ['infer'] + sys.argv[1:]",
    "runpy.run_module('infer', run_name='__main__', alter_sys=True)",
])


def disponivel() -> bool:
    return (REPO / "infer" / "__main__.py").exists() and (REPO / "models" / "params" / "apc.pth").exists()


def midi_amtapc(audio: Path, pasta: Path, nivel: str) -> Path:
    """MIDI do cover no estilo do nível (cache em <pasta>/cache/amtapc_<nivel>.mid)."""
    destino = pasta / "cache" / f"amtapc_{nivel}.mid"
    if destino.exists():
        print(f"[amt-apc] usando cache {destino.name}")
        return destino
    if not disponivel():
        raise RuntimeError("AMT-APC não instalado em modelos/amt-apc (veja amtapc.py)")
    destino.parent.mkdir(parents=True, exist_ok=True)
    print(f"[amt-apc] gerando cover ({ESTILO[nivel]})...")
    subprocess.run([sys.executable, "-X", "utf8", "-c", _RODAR_SEM_GPU, str(audio.resolve()), "-o",
                    str(destino.resolve()), "-s", ESTILO[nivel]], cwd=REPO, check=True)
    return destino


def maos_amtapc(audio: Path, pasta: Path, nivel: str, grade):
    """(mão direita, mão esquerda) quantizadas na grade atual, como no Pop2Piano."""
    import pretty_midi

    import gerar
    from pop2piano import _por_mao
    pm = pretty_midi.PrettyMIDI(str(midi_amtapc(audio, pasta, nivel)))
    notas = [n for inst in pm.instruments for n in inst.notes]
    passo = grade.passo
    return (_por_mao([n for n in notas if n.pitch >= 60], grade, passo),
            _por_mao([n for n in notas if n.pitch < 60], grade, passo))
