"""Gera um sample curto de várias vozes embutidas do XTTS-v2, pra comparar
timbre e escolher o narrador de um roteiro sem precisar sintetizar o vídeo
inteiro pra cada voz candidata.

Uso:
    python scripts/gerar_samples_vozes.py Projetos/Video_1/historia_humanidade/texto.md
    python scripts/gerar_samples_vozes.py Projetos/Video_1/historia_humanidade/texto.md --genero feminino
    python scripts/gerar_samples_vozes.py Projetos/Video_1/historia_humanidade/texto.md --vozes "Viktor Eka,Baldur Sanjin"

O texto do sample é o início do roteiro (primeiras frases até acumular
~`--palavras` palavras, respeitando limites de frase) — mesma técnica de
`gerar_video.agrupar_em_blocos`, só que sem alvo de duração medida (não faz
sentido medir taxa de palavras/segundo aqui: é justamente a taxa de cada
voz candidata que ainda não conhecemos). ~26 palavras dá uns 10s pra vozes
nessa faixa de 130-140 palavras/min observada no projeto; a duração real
varia um pouco de voz pra voz, é só uma estimativa.

Requer o servidor da plataforma rodando (`uvicorn server.main:app --port 8011`).
"""
from __future__ import annotations

import argparse
import re
import wave
from pathlib import Path

import pysbd
import requests

# Mesmo hack de gerar_video.py: o Synthesizer do Coqui TTS sempre segmenta
# frases com pysbd language="en" por baixo dos panos, mesmo sintetizando em
# outro idioma (pysbd não tem regras próprias de português).
_SEGMENTER_LANG = "en"

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")

# Classificação de gênero pelo nome, na mesma ordem em que a lista aparece
# em GET /api/voices (58 locutores embutidos do XTTS-v2, 29 de cada).
VOZES_MASCULINAS = [
    "Andrew Chipper", "Badr Odhiambo", "Dionisio Schuyler", "Royston Min",
    "Viktor Eka", "Abrahan Mack", "Adde Michal", "Baldur Sanjin",
    "Craig Gutsy", "Damien Black", "Gilberto Mathias", "Ilkin Urbano",
    "Kazuhiko Atallah", "Ludvig Milivoj", "Suad Qasim", "Torcull Diarmuid",
    "Viktor Menelaos", "Zacharie Aimilios", "Ige Behringer", "Filip Traverse",
    "Damjan Chapman", "Wulf Carlevaro", "Aaron Dreschner", "Kumar Dahl",
    "Eugenio Mataracı", "Ferran Simen", "Xavier Hayasaka", "Luis Moray",
    "Marcos Rudaski",
]

VOZES_FEMININAS = [
    "Claribel Dervla", "Daisy Studious", "Gracie Wise", "Tammie Ema",
    "Alison Dietlinde", "Ana Florence", "Annmarie Nele", "Asya Anara",
    "Brenda Stern", "Gitta Nikolina", "Henriette Usha", "Sofia Hellen",
    "Tammy Grit", "Tanja Adelina", "Vjollca Johnnie", "Nova Hogarth",
    "Maja Ruoho", "Uta Obando", "Lidiya Szekeres", "Chandra MacFarland",
    "Szofi Granger", "Camilla Holmström", "Lilya Stainthorpe",
    "Zofija Kendrick", "Narelle Moon", "Barbora MacLean",
    "Alexandra Hisakawa", "Alma María", "Rosemary Okafor",
]


def duracao_wav(caminho: Path) -> float:
    with wave.open(str(caminho), "rb") as f:
        return f.getnframes() / float(f.getframerate())


def extrair_texto_amostra(roteiro: str, palavras_alvo: int) -> str:
    segmentador = pysbd.Segmenter(language=_SEGMENTER_LANG, clean=True)
    frases = [f.strip() for f in segmentador.segment(roteiro) if f.strip()]
    escolhidas: list[str] = []
    total_palavras = 0
    for frase in frases:
        escolhidas.append(frase)
        total_palavras += len(frase.split())
        if total_palavras >= palavras_alvo:
            break
    return " ".join(escolhidas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roteiro", type=Path, help="Caminho do .md/.txt com o texto da narração")
    ap.add_argument("--genero", choices=["masculino", "feminino"], default="masculino")
    ap.add_argument("--vozes", default=None, help="Lista separada por vírgula, sobrepõe --genero")
    ap.add_argument("--palavras", type=int, default=26, help="Palavras do início do roteiro usadas no sample (~10s)")
    ap.add_argument("--idioma", default="pt")
    ap.add_argument("--server", default="http://127.0.0.1:8011")
    ap.add_argument("--saida", type=Path, default=None, help="Pasta do projeto (padrão: pasta do roteiro)")
    args = ap.parse_args()

    if not args.roteiro.exists():
        raise SystemExit(f"Roteiro não encontrado: {args.roteiro}")

    if args.vozes:
        vozes = [v.strip() for v in args.vozes.split(",") if v.strip()]
    else:
        vozes = VOZES_MASCULINAS if args.genero == "masculino" else VOZES_FEMININAS

    texto = extrair_texto_amostra(args.roteiro.read_text(encoding="utf-8").strip(), args.palavras)
    print(f'Texto do sample ({len(texto.split())} palavras): "{texto}"\n')

    projeto = args.saida or args.roteiro.parent
    dir_samples = projeto / "samples_vozes"
    dir_samples.mkdir(parents=True, exist_ok=True)

    resultados = []
    for i, voz in enumerate(vozes, start=1):
        nome_arquivo = _SAFE_NAME_RE.sub("_", voz).strip("_")
        destino = dir_samples / f"{nome_arquivo}.wav"
        print(f"[{i}/{len(vozes)}] {voz}...", end=" ", flush=True)
        try:
            resp = requests.post(
                f"{args.server}/api/synthesize",
                json={"texto": texto, "voice_id": voz, "language": args.idioma, "normalizar": False},
                timeout=120,
            )
            resp.raise_for_status()
            dados = resp.json()
            audio = requests.get(f"{args.server}{dados['audio_url']}", timeout=60)
            audio.raise_for_status()
            destino.write_bytes(audio.content)
        except requests.exceptions.ConnectionError as e:
            raise SystemExit(
                f"\nNão consegui falar com o servidor em {args.server}. "
                "Ele está rodando? (uvicorn server.main:app --port 8011)"
            ) from e
        dur = duracao_wav(destino)
        print(f"-> {destino.name} ({dur:.1f}s)")
        resultados.append((voz, destino.name, dur))

    print(f"\n{len(resultados)} sample(s) em {dir_samples}/")


if __name__ == "__main__":
    main()
