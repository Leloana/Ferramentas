"""Reavalia o alinhamento da letra das músicas em `server/songs/` e regrava
`meta.json["alignment_quality"]` e `["needs_review"]` (utils/alignment_quality.py).

Acha as letras "boas de transcrição, porém deslocadas": verso com palavras
espalhadas por igual, verso fora do tempo do Whisper do stem de voz
(`.structure_words.json`, sem GPU) e palavras grudadas. A lista da TV mostra
"Revisar" nas marcadas (menos nas que já foram revisadas no editor).
Pode rodar com o servidor ligado.

    python tools/audit_alignment.py            # todas as músicas
    python tools/audit_alignment.py <slug>...  # só essas
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
from utils.alignment_quality import record_alignment_quality  # noqa: E402
from utils.song_paths import USER_EDITED_MARKER  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(slugs: list[str]) -> None:
    songs = ROOT / "server" / "songs"
    dirs = [songs / s for s in slugs] if slugs else sorted(p for p in songs.iterdir() if p.is_dir())
    flagged = []
    for song_dir in dirs:
        if not (song_dir / "segments.json").exists():
            continue
        quality = record_alignment_quality(song_dir)
        if quality is None:
            continue
        meta = json.loads((song_dir / "meta.json").read_text(encoding="utf-8")) if (song_dir / "meta.json").exists() else {}
        if meta.get("needs_review"):
            edited = " (revisada no editor)" if (song_dir / USER_EDITED_MARKER).exists() else ""
            severe = quality.get("severe_lines") or []
            flagged.append(f"{song_dir.name}: nota {quality['score']}, {len(severe)} verso(s) grave(s) "
                           f"{[i + 1 for i in severe][:12]}{edited}")
    print(f"{len(flagged)} de {len(dirs)} música(s) para revisar")
    for line in flagged:
        print("  " + line)


if __name__ == "__main__":
    main(sys.argv[1:])
