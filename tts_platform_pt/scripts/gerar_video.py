"""Automatiza a geração de áudio a partir de um roteiro em texto, usando a
Plataforma de TTS local (POST /api/synthesize).

Uso:
    python scripts/gerar_video.py Projetos/Video_1/historia_humanidade/texto.md

Fluxo:
1. Sintetiza o roteiro inteiro, exatamente como está no arquivo (sem
   agrupar/cortar em blocos) -> salva em <projeto>/audio/.
2. Guarda no manifesto a duração medida e os timestamps por frase (usados
   depois por gerar_imagens.py e montar_video.py).

Voz padrão é a masculina (Dionisio Schuyler) — a versão feminina só é
gerada se pedida explicitamente com --voz. Velocidade padrão é 1.20 (speed
nativo do XTTS-v2, ver server/engine/tts_engine.py) — cadência mais ágil que
o 1.0 "neutro" do modelo, escolhida ouvindo amostras lado a lado (ver
Projetos/testes_velocidade/); passe --velocidade 1.0 pra voltar ao padrão do
modelo.

Requer o servidor da plataforma rodando (`uvicorn server.main:app --port 8011`).
"""
from __future__ import annotations

import argparse
import json
import wave
from datetime import datetime
from pathlib import Path

import requests

_VOZ_PADRAO = "Dionisio Schuyler"
_VELOCIDADE_PADRAO = 1.20


def duracao_wav(caminho: Path) -> float:
    with wave.open(str(caminho), "rb") as f:
        return f.getnframes() / float(f.getframerate())


def sintetizar(server: str, texto: str, voz: str | None, idioma: str, normalizar: bool, velocidade: float, destino: Path) -> dict:
    resp = requests.post(
        f"{server}/api/synthesize",
        json={"texto": texto, "voice_id": voz, "language": idioma, "normalizar": normalizar, "speed": velocidade},
        timeout=600,
    )
    resp.raise_for_status()
    dados = resp.json()

    audio = requests.get(f"{server}{dados['audio_url']}", timeout=120)
    audio.raise_for_status()
    destino.write_bytes(audio.content)

    dados["duracao_s"] = duracao_wav(destino)
    return dados


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roteiro", type=Path, help="Caminho do .md/.txt com o texto da narração")
    ap.add_argument("--voz", default=_VOZ_PADRAO,
                     help='Nome do locutor embutido ou "custom:<arquivo>.wav" '
                          f'(padrão: "{_VOZ_PADRAO}", voz masculina; passe --voz "Ana Florence" '
                          'pra gerar a versão feminina)')
    ap.add_argument("--idioma", default="pt")
    ap.add_argument("--normalizar", action="store_true", help="Ativa a normalização via Ollama (desativada por padrão)")
    ap.add_argument("--velocidade", type=float, default=_VELOCIDADE_PADRAO,
                     help=f"speed nativo do XTTS-v2, ~0.7-1.3 sem degradar a voz (padrão: {_VELOCIDADE_PADRAO})")
    ap.add_argument("--server", default="http://127.0.0.1:8011")
    ap.add_argument("--saida", type=Path, default=None, help="Pasta do projeto (padrão: pasta do roteiro)")
    args = ap.parse_args()

    if not args.roteiro.exists():
        raise SystemExit(f"Roteiro não encontrado: {args.roteiro}")

    projeto = args.saida or args.roteiro.parent
    dir_audio = projeto / "audio"
    dir_audio.mkdir(parents=True, exist_ok=True)

    nome_base = args.roteiro.stem
    texto = args.roteiro.read_text(encoding="utf-8").strip()

    try:
        print(f"Sintetizando áudio ({len(texto.split())} palavras, voz \"{args.voz}\", velocidade {args.velocidade})...")
        caminho_audio = dir_audio / f"{nome_base}.wav"
        info = sintetizar(args.server, texto, args.voz, args.idioma, args.normalizar, args.velocidade, caminho_audio)
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(
            f"Não consegui falar com o servidor em {args.server}. "
            "Ele está rodando? (uvicorn server.main:app --port 8011)"
        ) from e
    print(f"    -> {caminho_audio.name} ({info['duracao_s']:.1f}s)")
    if info["aviso_normalizacao"]:
        print(f"    aviso: {info['aviso_normalizacao']}")

    manifesto = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "roteiro": str(args.roteiro),
        "voz": args.voz,
        "idioma": args.idioma,
        "normalizar": args.normalizar,
        "velocidade": args.velocidade,
        "arquivo": f"audio/{caminho_audio.name}",
        "duracao_s": round(info["duracao_s"], 1),
        "texto_usado": info["texto_usado"],
        "aviso_normalizacao": info["aviso_normalizacao"],
        "frases": info["frases"],
    }
    caminho_manifesto = projeto / f"{nome_base}_manifesto.json"
    caminho_manifesto.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifesto salvo em {caminho_manifesto}")


if __name__ == "__main__":
    main()
