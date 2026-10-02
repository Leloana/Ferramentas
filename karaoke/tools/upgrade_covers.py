"""Baixa de novo, em resolução maior, as capas que já estão em `server/songs/`.

As capas antigas vinham do iTunes em 600x600 (ou da miniatura 480x360 do YouTube) e
ficavam borradas no cartão do fim da música. Este script troca cada uma pela versão
grande da MESMA imagem (iTunes 1200, YouTube 1280x720); a escolha feita na TV vale.
Só biblioteca padrão; precisa de internet. Pode rodar com o servidor ligado.

    python tools/upgrade_covers.py            # todas as músicas
    python tools/upgrade_covers.py <slug>...  # só essas
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
from utils.cover import upgrade_cover  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(slugs: list[str]) -> None:
    songs = ROOT / "server" / "songs"
    dirs = [songs / s for s in slugs] if slugs else sorted(p for p in songs.iterdir() if p.is_dir())
    changed = 0
    for song_dir in dirs:
        if upgrade_cover(song_dir):
            changed += 1
            print(f"capa maior: {song_dir.name}")
    print(f"{changed} capa(s) trocada(s) de {len(dirs)} música(s)")


if __name__ == "__main__":
    main(sys.argv[1:])
