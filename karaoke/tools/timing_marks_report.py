"""Junta as palavras marcadas com tempo errado (anotação do fim de jogo) por música.

    # todas as músicas com marcas
    python tools/timing_marks_report.py
    # uma música, incluindo as suspeitas não marcadas (cantadas a mais de 0,8 s da letra)
    python tools/timing_marks_report.py 505-arctic-monkeys --suspeitas

Para cada palavra: o tempo da letra hoje (`songs/<slug>/segments.json`), o tempo em
que o cantor cantou (mediana das partidas) e a diferença. Diferença positiva = a
letra está adiantada (o cantor entrou depois). Verso cuja letra mudou desde a
partida aparece como "letra mudou" e fica sem comparação.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from recorder import SESSION_FILE, load_timing_marks, recording_base_dir, sung_word_times  # noqa: E402

SONGS_DIR = ROOT / "server" / "songs"
SUSPECT_GAP_SEC = 0.8  # mesmo limite do annotate.js


def fmt(sec: float | None) -> str:
    if sec is None:
        return "  —  "
    m = int(sec // 60)
    return f"{m}:{sec - m * 60:04.1f}"


def current_segments(slug: str) -> list[dict] | None:
    path = SONGS_DIR / slug / "segments.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def collect(base: Path, only_song: str | None, suspects: bool) -> dict:
    """{slug: {(verso, palavra): {"word", "lyrics", "sung": [..], "marked": n}}}"""
    songs: dict = defaultdict(dict)
    for session_dir in sorted(d for d in base.iterdir() if (d / SESSION_FILE).is_file()):
        session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
        slug = session["song_id"]
        if only_song and slug != only_song:
            continue
        marks = load_timing_marks(session_dir)
        if not marks and not suspects:
            continue
        results = {(r["player"], r["segment"]): r for r in session["results"]}
        for player in session["players"]:
            player_marks = marks.get(player, {})
            for idx, seg in enumerate(session["segments"]):
                r = results.get((player, idx))
                if not r:
                    continue
                words = sung_word_times(seg, r)
                marked = set(player_marks.get(str(idx + 1), []))
                for i, w in enumerate(words):
                    suspect = w["sung"] is not None and abs(w["sung"] - w["expected"]) > SUSPECT_GAP_SEC
                    if i not in marked and not (suspects and suspect):
                        continue
                    item = songs[slug].setdefault((idx + 1, i), {
                        "word": w["word"], "lyrics": seg["lyrics"], "sung": [], "marked": 0,
                    })
                    if w["sung"] is not None:
                        item["sung"].append(w["sung"])
                    item["marked"] += i in marked
    return songs


def report(songs: dict) -> None:
    if not songs:
        print("Nenhuma palavra marcada.")
        return
    for slug, words in sorted(songs.items()):
        segments = current_segments(slug)
        print(f"\n{slug}")
        print("  verso  palavra            letra   cantei   dif.   marcas")
        for (n, i), item in sorted(words.items()):
            seg = segments[n - 1] if segments and n <= len(segments) else None
            if not seg or seg.get("lyrics") != item["lyrics"]:
                print(f"  {n:>5}  {item['word']:<16}  letra mudou")
                continue
            w = seg["lyrics_timed"][i]
            expected = seg["sing_start"] + w["expected_start"]
            sung = statistics.median(item["sung"]) if item["sung"] else None
            gap = f"{sung - expected:+.2f}" if sung is not None else "  —  "
            print(f"  {n:>5}  {item['word']:<16} {fmt(expected):>7}  {fmt(sung):>7}  {gap:>6}  "
                  f"{item['marked']}/{len(item['sung']) or 1}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("song", nargs="?", help="slug da música (padrão: todas)")
    parser.add_argument("--suspeitas", action="store_true", help="inclui palavras cantadas longe do tempo, mesmo sem marca")
    args = parser.parse_args()
    base = recording_base_dir()
    if base is None or not base.is_dir():
        print("Sem pasta de gravações.")
        return
    report(collect(base, args.song, args.suspeitas))


if __name__ == "__main__":
    main()
