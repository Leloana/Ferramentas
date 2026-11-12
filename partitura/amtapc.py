"""Arranjo de piano com o AMT-APC (310hz/amt-apc, 2024): IA que gera "piano cover" a partir da música,
com 3 estilos que casam com os níveis: level1 = fácil, level2 = médio, level3 = difícil.

Instalação (fora do git, em modelos/):
  git clone https://github.com/310hz/amt-apc modelos/amt-apc
  curl -L -o modelos/amt-apc/models/params/apc.pth https://github.com/310hz/amt-apc/releases/download/beta/apc.pth
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REPO = AQUI / "modelos" / "amt-apc"
ESTILO = {"facil": "level1", "medio": "level2", "dificil": "level3"}


# o checkpoint do AMT-APC foi salvo com os pesos na GPU: sem placa, torch.load falha. Este
# lançador roda o `infer` do repositório mapeando os pesos pra CPU quando não há CUDA (modo leve)
_RODAR_SEM_GPU = "\n".join([
    "import os, sys, runpy, torch",
    # todos os núcleos lógicos: ~10% mais rápido em CPU, notas idênticas (medido 2026-11-11; a
    # quantização int8 acelerava mais, mas mudava 15% das notas, então ficou de fora)
    "torch.set_num_threads(os.cpu_count() or 1)",
    "if not torch.cuda.is_available() or torch.cuda.device_count() == 0:",
    "    _carregar = torch.load",
    "    torch.load = lambda *a, **k: _carregar(*a, **{**k, 'map_location': 'cpu'})",
    # torchaudio >= 2.9 carrega áudio pelo torchcodec; sem ele, lê com soundfile (mesmo formato)
    "import torchaudio",
    "try:",
    "    import torchcodec  # noqa: F401",
    "except Exception:",
    "    import soundfile",
    "    def _ler(caminho, *a, **k):",
    "        dados, sr = soundfile.read(str(caminho), dtype='float32', always_2d=True)",
    "        return torch.from_numpy(dados.T.copy()), sr",
    "    torchaudio.load = _ler",
    "sys.argv = ['infer'] + sys.argv[1:]",
    "runpy.run_module('infer', run_name='__main__', alter_sys=True)",
])


# Serviço com o modelo já carregado (o site sobe um no início): carregar o AMT-APC custa ~8 s por música.
# O gerar.py acha o serviço pela variável PARTITURA_AMTAPC ("host:porta"); sem ela, ou se o serviço não
# responder, roda o lançador acima como antes (mesmo vetor de estilo, mesmas notas).
VARIAVEL = "PARTITURA_AMTAPC"


def _pelo_servico(audio: Path, destino: Path, estilo: str) -> bool:
    """Pede o MIDI ao serviço; repassa as linhas de progresso (a barra do site lê os segmentos). False se não há serviço."""
    endereco = os.environ.get(VARIAVEL)
    if not endereco:
        return False
    host, porta = endereco.rsplit(":", 1)
    try:
        conexao = socket.create_connection((host, int(porta)), timeout=3)
    except OSError:
        return False
    with conexao:
        conexao.settimeout(None)
        pedido = {"audio": str(audio.resolve()), "destino": str(destino.resolve()), "estilo": estilo}
        conexao.sendall((json.dumps(pedido) + "\n").encode("utf-8"))
        with conexao.makefile("r", encoding="utf-8", newline="\n") as resposta:
            for linha in resposta:
                linha = linha.rstrip("\n")
                if linha == "#OK":
                    return True
                if linha.startswith("#ERRO"):
                    raise RuntimeError(f"AMT-APC (serviço): {linha[6:]}")
                print(linha, file=sys.stderr, flush=True)
    raise RuntimeError("AMT-APC (serviço): conexão caiu no meio")


def servir(porta: int, host: str = "127.0.0.1"):
    """Carrega o modelo uma vez e atende um pedido por vez: {"audio", "destino", "estilo"} numa linha JSON;
    devolve as linhas do tqdm e por fim "#OK" ou "#ERRO <motivo>"."""
    exec(compile(_RODAR_SEM_GPU.rsplit("\nsys.argv", 1)[0], "amtapc_preparo", "exec"), {})
    sys.path.insert(0, str(REPO))
    os.chdir(REPO)
    import torch
    from data import SVSampler
    from models import Pipeline
    from utils import config
    pipe = Pipeline(config.path.apc, torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    amostrador = SVSampler()

    class _Repasse:
        def __init__(self, arq):
            self.arq = arq

        def write(self, texto):
            for parte in texto.replace("\r", "\n").split("\n"):
                if parte.strip():
                    self.arq.write(parte + "\n")
                    self.arq.flush()
            return len(texto)

        def flush(self):
            pass

    escuta = socket.create_server((host, porta))
    print(f"[amt-apc] serviço pronto em {host}:{porta}", flush=True)
    while True:
        conexao, _ = escuta.accept()
        with conexao, conexao.makefile("rw", encoding="utf-8", newline="\n") as arq:
            try:
                pedido = json.loads(arq.readline())
                destino = Path(pedido["destino"])
                tmp = destino.with_suffix(".tmp.mid")
                erro_antes = sys.stderr
                sys.stderr = _Repasse(arq)
                try:
                    with torch.no_grad():
                        pipe.wav2midi(pedido["audio"], str(tmp), amostrador.sample(params=pedido["estilo"]),
                                      silent=False)
                finally:
                    sys.stderr = erro_antes
                tmp.replace(destino)
                arq.write("#OK\n")
            except Exception as e:  # noqa: BLE001
                try:
                    arq.write(f"#ERRO {type(e).__name__}: {e}\n".replace("\n", " ").rstrip() + "\n")
                except OSError:
                    pass
            try:
                arq.flush()
            except OSError:
                pass


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
    print(f"[amt-apc] gerando cover ({ESTILO[nivel]})...", flush=True)
    if _pelo_servico(audio, destino, ESTILO[nivel]):
        return destino
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


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="serviço do AMT-APC com o modelo carregado")
    ap.add_argument("--servico", type=int, required=True, metavar="PORTA")
    servir(ap.parse_args().servico)
