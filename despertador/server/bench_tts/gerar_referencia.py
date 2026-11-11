"""Gera na ElevenLabs o áudio de referência (voz David, tom animado) usado para clonar a voz localmente.

O áudio não vai para o git (repositório público); cada máquina gera o seu com a chave do `server/.env`.
Custa ~40 créditos na primeira vez e fica no cache de `server/data/cache_tts` (repetir não gasta).

Uso (de despertador/server):  .venv/bin/python bench_tts/gerar_referencia.py
Saída: bench_tts/saida/ref/david_animado.wav (24 kHz mono) e david_animado.txt (transcrição exata).
"""
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
import config  # noqa: E402
import voz  # noqa: E402

# Mais expressivo que o padrão da narração (0.5 / 0.2): a referência dita o tom e o ritmo do clone.
AJUSTES = {"stability": 0.3, "similarity_boost": 0.75, "style": 0.6}
TEXTO = ("Bom dia, bom dia! Que bom ter você aqui. Pega o seu café, respira fundo... "
         "e vem comigo, que hoje tem notícia boa pra começar o dia. Primeiro, a economia. "
         "Depois, as novidades do clima. Vamos nessa?")


def main() -> None:
    destino = AQUI / "saida" / "ref"
    destino.mkdir(parents=True, exist_ok=True)
    mp3, wav = destino / "david_animado.mp3", destino / "david_animado.wav"
    config.ELEVEN_AJUSTES = AJUSTES
    chamou = voz.sintetizar(TEXTO, mp3, motivo="referência animada para clonagem local")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", "24000", str(wav)],
                   check=True)
    (destino / "david_animado.txt").write_text(TEXTO, encoding="utf-8")
    print(f"{wav} ({'ElevenLabs' if chamou else 'cache'}; gasto total {voz.gasto_total()} créditos)")


if __name__ == "__main__":
    main()
