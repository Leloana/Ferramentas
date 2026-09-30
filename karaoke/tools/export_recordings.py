"""Vira partidas gravadas e anotadas em fixtures de teste, e faz backup.

    # fixtures de todas as partidas anotadas de karaoke/recordings/
    python tools/export_recordings.py
    # também as sem anotação (para olhar/replay; não viram teste)
    python tools/export_recordings.py --all
    # backup: todas as partidas (com os .wav) num zip
    python tools/export_recordings.py --zip D:/backup/karaoke-gravacoes.zip

Cada cantor anotado vira `tests/fixtures/recorded_sessions/exported/<data>_<música>_<cantor>.json`,
no mesmo formato das fixtures antigas + `labels` (gabarito) e `baseline` (erro médio da nota de
hoje contra o gabarito). O teste `test_exported_sessions_do_not_regress` falha se uma mudança no
score piorar esse erro — assim cada partida anotada vira proteção contra regressão.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from calibration import label_mae, rescore_session  # noqa: E402
from recorder import SESSION_FILE, load_labels, recording_base_dir, _safe_name  # noqa: E402

DEFAULT_OUT = ROOT / "tests" / "fixtures" / "recorded_sessions" / "exported"
KEEP_FIELDS = ("words", "prompted_words", "unprompted_words", "used", "pitch", "rms")


def sessions_in(paths: list[Path]) -> list[Path]:
    found = []
    for p in paths:
        if (p / SESSION_FILE).is_file():
            found.append(p)
        elif p.is_dir():
            found.extend(sorted(d for d in p.iterdir() if (d / SESSION_FILE).is_file()))
    return found


def fixture_for(session_dir: Path, session: dict, player: str, labels: dict) -> dict:
    results = []
    for r in session["results"]:
        if r["player"] != player:
            continue
        entry = {"segment": r["segment"], "live_score": r["score"]}
        entry.update({k: r[k] for k in KEEP_FIELDS if k in r})
        results.append(entry)
    fixture = {
        "song_id": session["song_id"],
        "recorded_at": session.get("started_at"),
        "whisper_model": session.get("whisper_model"),
        "scoring_mode": session.get("scoring_mode", "timing"),
        "segments": session["segments"],
        "results": results,
        "labels": labels,
        "source": {"session": session_dir.name, "player": player,
                   "commit": (session.get("versions") or {}).get("commit")},
    }
    scores, _ = rescore_session(fixture)
    mae, n = label_mae(scores, labels)
    fixture["baseline"] = {"mae": mae, "labeled_verses": n}
    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path, help="Partidas ou pasta com várias (padrão: recordings/)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Pasta das fixtures")
    parser.add_argument("--all", action="store_true", help="Exporta também cantores sem anotação")
    parser.add_argument("--zip", type=Path, help="Em vez de fixtures, empacota as partidas (com .wav) neste zip")
    args = parser.parse_args()

    base = args.paths or [recording_base_dir() or ROOT / "recordings"]
    sessions = sessions_in(base)
    if not sessions:
        print("Nenhuma partida gravada encontrada.")
        return 1

    if args.zip:
        args.zip.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for d in sessions:
                for f in d.rglob("*"):
                    if f.is_file():
                        zf.write(f, f"{d.name}/{f.relative_to(d)}")
        print(f"{len(sessions)} partida(s) em {args.zip}")
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    written = 0
    for d in sessions:
        session = json.loads((d / SESSION_FILE).read_text(encoding="utf-8"))
        all_labels = load_labels(d)
        players = sorted({r["player"] for r in session["results"]})
        for player in players:
            labels = all_labels.get(player) or {}
            if not labels and not args.all:
                continue
            fixture = fixture_for(d, session, player, labels)
            name = f"{d.name}_{_safe_name(player)}.json"
            (args.out / name).write_text(json.dumps(fixture, ensure_ascii=False, indent=1), encoding="utf-8")
            base_info = fixture["baseline"]
            print(f"{name}: {len(fixture['results'])} versos, {base_info['labeled_verses']} anotados, "
                  f"erro médio {base_info['mae']}")
            written += 1
    print(f"{written} fixture(s) em {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
