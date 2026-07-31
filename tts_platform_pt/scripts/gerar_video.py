"""Automatiza a geração de áudio (vídeo longo + partes curtas) a partir de um
roteiro em texto, usando a Plataforma de TTS local (POST /api/synthesize).

Uso:
    python scripts/gerar_video.py Projetos/video-curto/humanidade.md --voz "Ana Florence"

Fluxo:
1. Sintetiza o roteiro inteiro de uma vez só -> salva em <projeto>/video-longo/.
2. Mede a duração real desse áudio e calcula a taxa de palavras/segundo dessa
   voz nesse texto (evita chutar uma taxa fixa: cada voz/normalização fala
   num ritmo diferente).
3. Usa essa taxa pra agrupar as frases do roteiro (respeitando limites de
   frase) em blocos de ~N minutos.
4. Sintetiza cada bloco separadamente -> salva em <projeto>/video-curto/,
   numerados.

Requer o servidor da plataforma rodando (`uvicorn server.main:app --port 8011`).
"""
from __future__ import annotations

import argparse
import json
import wave
from datetime import datetime
from pathlib import Path

import pysbd
import requests

# A classe Synthesizer do Coqui TTS sempre usa o segmentador de frases do
# pysbd com language="en" (hardcoded em TTS/utils/synthesizer.py, mesmo
# sintetizando em outro idioma) porque o pysbd não tem regras próprias pra
# português. Usamos o mesmo aqui pra cortar as frases exatamente como o
# motor corta por baixo dos panos, em vez de arriscar um segmentador
# diferente que ache limites de frase em lugares diferentes.
_SEGMENTER_LANG = "en"


def duracao_wav(caminho: Path) -> float:
    with wave.open(str(caminho), "rb") as f:
        return f.getnframes() / float(f.getframerate())


def sintetizar(server: str, texto: str, voz: str | None, idioma: str, normalizar: bool, destino: Path) -> dict:
    resp = requests.post(
        f"{server}/api/synthesize",
        json={"texto": texto, "voice_id": voz, "language": idioma, "normalizar": normalizar},
        timeout=600,
    )
    resp.raise_for_status()
    dados = resp.json()

    audio = requests.get(f"{server}{dados['audio_url']}", timeout=120)
    audio.raise_for_status()
    destino.write_bytes(audio.content)

    dados["duracao_s"] = duracao_wav(destino)
    return dados


def agrupar_em_blocos(frases: list[str], palavras_por_segundo: float, segundos_por_bloco: float) -> list[str]:
    """Agrupa frases em blocos de ~segundos_por_bloco, sem cortar no meio de uma frase."""
    alvo_palavras = palavras_por_segundo * segundos_por_bloco
    blocos: list[list[str]] = []
    atual: list[str] = []
    palavras_atual = 0
    for frase in frases:
        atual.append(frase)
        palavras_atual += len(frase.split())
        if palavras_atual >= alvo_palavras:
            blocos.append(atual)
            atual = []
            palavras_atual = 0
    if atual:
        # Sobra pequena no final: gruda no bloco anterior em vez de virar uma
        # "parte extra" de poucos segundos.
        if blocos and palavras_atual < alvo_palavras * 0.4:
            blocos[-1].extend(atual)
        else:
            blocos.append(atual)
    return [" ".join(b) for b in blocos]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roteiro", type=Path, help="Caminho do .md/.txt com o texto da narração")
    ap.add_argument("--voz", default=None, help='Nome do locutor embutido (ex.: "Ana Florence") ou "custom:<arquivo>.wav"')
    ap.add_argument("--idioma", default="pt")
    ap.add_argument("--normalizar", action="store_true", help="Ativa a normalização via Ollama (desativada por padrão)")
    ap.add_argument("--minutos-por-parte", type=float, default=1.0)
    ap.add_argument("--server", default="http://127.0.0.1:8011")
    ap.add_argument("--saida", type=Path, default=None, help="Pasta do projeto (padrão: pasta do roteiro)")
    args = ap.parse_args()

    if not args.roteiro.exists():
        raise SystemExit(f"Roteiro não encontrado: {args.roteiro}")

    projeto = args.saida or args.roteiro.parent
    dir_longo = projeto / "video-longo"
    dir_curto = projeto / "video-curto"
    dir_longo.mkdir(parents=True, exist_ok=True)
    dir_curto.mkdir(parents=True, exist_ok=True)

    nome_base = args.roteiro.stem
    texto = args.roteiro.read_text(encoding="utf-8").strip()

    try:
        print(f"[1/2] Sintetizando vídeo longo ({len(texto.split())} palavras)...")
        caminho_longo = dir_longo / f"{nome_base}.wav"
        info_longo = sintetizar(args.server, texto, args.voz, args.idioma, args.normalizar, caminho_longo)
    except requests.exceptions.ConnectionError as e:
        raise SystemExit(
            f"Não consegui falar com o servidor em {args.server}. "
            "Ele está rodando? (uvicorn server.main:app --port 8011)"
        ) from e
    duracao_longo = info_longo["duracao_s"]
    print(f"    -> {caminho_longo.name} ({duracao_longo:.1f}s)")
    if info_longo["aviso_normalizacao"]:
        print(f"    aviso: {info_longo['aviso_normalizacao']}")

    palavras_por_segundo = len(texto.split()) / duracao_longo
    print(f"    taxa medida: {palavras_por_segundo * 60:.0f} palavras/min")

    segmentador = pysbd.Segmenter(language=_SEGMENTER_LANG, clean=True)
    frases = [f.strip() for f in segmentador.segment(texto) if f.strip()]
    blocos = agrupar_em_blocos(frases, palavras_por_segundo, args.minutos_por_parte * 60)

    print(f"[2/2] Sintetizando {len(blocos)} parte(s) curta(s) (~{args.minutos_por_parte:.0f} min cada)...")
    manifesto_partes = []
    for i, bloco_texto in enumerate(blocos, start=1):
        caminho_parte = dir_curto / f"{nome_base}_{i:02d}.wav"
        info = sintetizar(args.server, bloco_texto, args.voz, args.idioma, args.normalizar, caminho_parte)
        print(f"    -> {caminho_parte.name} ({info['duracao_s']:.1f}s)")
        if info["aviso_normalizacao"]:
            print(f"       aviso: {info['aviso_normalizacao']}")
        manifesto_partes.append({
            "arquivo": caminho_parte.name,
            "duracao_s": round(info["duracao_s"], 1),
            "texto": bloco_texto,
            "texto_usado": info["texto_usado"],
            "aviso_normalizacao": info["aviso_normalizacao"],
        })

    manifesto = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "roteiro": str(args.roteiro),
        "voz": args.voz,
        "idioma": args.idioma,
        "normalizar": args.normalizar,
        "video_longo": {
            "arquivo": f"video-longo/{caminho_longo.name}",
            "duracao_s": round(duracao_longo, 1),
            "texto_usado": info_longo["texto_usado"],
            "aviso_normalizacao": info_longo["aviso_normalizacao"],
        },
        "video_curto": manifesto_partes,
    }
    caminho_manifesto = projeto / f"{nome_base}_manifesto.json"
    caminho_manifesto.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifesto salvo em {caminho_manifesto}")


if __name__ == "__main__":
    main()
