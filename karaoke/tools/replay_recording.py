"""Pontua de novo partidas gravadas (server/recorder.py), sem precisar cantar.

Usa o mesmo recorte de janela e a mesma nota do servidor (mic_stream +
segment_scoring), trocando só o que for pedido na linha de comando:

    # Todas as partidas de karaoke/recordings/, com os parâmetros atuais
    python tools/replay_recording.py

    # Uma partida, outro modelo e um limiar alterado
    python tools/replay_recording.py recordings/20260929-221500_plug-in-baby-muse \\
        --model medium --set stt_engine._HARD_FLOOR=0.1

`--set modulo.NOME=valor` troca qualquer constante (valor em sintaxe Python).

Gabarito opcional: `gabarito.json` na pasta da partida. O botão ✎ discreto da
tela de fim de jogo grava as anotações do cantor (certo = 100, errado e
cantarolei = 0). Também dá para escrever à mão a nota esperada por verso
(numeração a partir de 1), por jogador ou para todos:

    {"3": 0, "4": 100}              ou   {"Lelo": {"3": 0, "4": 100}}

Com gabarito, a tabela mostra a nota esperada e o erro médio (MAE).
"""
from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for path in (PROJECT_ROOT, PROJECT_ROOT / "server"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import utils.cuda_bootstrap  # noqa: E402,F401  (registra as DLLs do CUDA antes do Whisper)
import torch  # noqa: E402,F401  (cuDNN 9.1 do torch antes do 9.10 do ctranslate2: na ordem inversa a 1ª conv na GPU derruba o processo)

import numpy as np  # noqa: E402

from mic_stream import segment_window  # noqa: E402
from recorder import DEFAULT_RECORD_DIR, GABARITO_FILE, SESSION_FILE, covered_mask, read_wav  # noqa: E402
import segment_scoring  # noqa: E402



def find_sessions(paths: list[str]) -> list[Path]:
    """Pastas de partida dadas, ou todas as de dentro das pastas dadas."""
    roots = [Path(p) for p in paths] or [DEFAULT_RECORD_DIR]
    sessions = []
    for root in roots:
        if (root / SESSION_FILE).exists():
            sessions.append(root)
        elif root.is_dir():
            sessions.extend(sorted(p for p in root.iterdir() if (p / SESSION_FILE).exists()))
        else:
            raise SystemExit(f"Não encontrei partida gravada em {root}")
    return sessions


def apply_overrides(overrides: list[str]) -> None:
    for item in overrides:
        target, _, raw = item.partition("=")
        module_name, _, attr = target.rpartition(".")
        if not module_name or not raw:
            raise SystemExit(f"--set espera modulo.NOME=valor, recebeu {item!r}")
        module = importlib.import_module(module_name)
        if not hasattr(module, attr):
            raise SystemExit(f"{module_name} não tem {attr}")
        setattr(module, attr, ast.literal_eval(raw))


LABEL_EXPECTED_SCORE = {"certo": 100.0, "errado": 0.0, "cantarolei": 0.0}


def load_gabarito(session_dir: Path, player: str) -> dict[int, float]:
    """Nota esperada por verso (índice a partir de 0).

    Aceita o gabarito anotado na tela final ({"labels": {jogador: {"3": "certo"}}})
    ou notas escritas à mão ({"3": 0} / {"Lelo": {"3": 0}}).
    """
    path = session_dir / GABARITO_FILE
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if "labels" in data:
        labels = data["labels"].get(player, {})
        return {int(k) - 1: LABEL_EXPECTED_SCORE[v] for k, v in labels.items() if v in LABEL_EXPECTED_SCORE}
    if player in data and isinstance(data[player], dict):
        data = data[player]
    return {int(k) - 1: float(v) for k, v in data.items() if not isinstance(v, dict)}


def replay_player(session: dict, audio: np.ndarray, covered: np.ndarray, stt, scoring_mode: str,
                  pre_sec: float, post_sec: float) -> dict[int, dict]:
    """Nota de cada verso, recortando a janela como o _dispatch_due_segments."""
    segments = session["segments"]
    sr = session["sample_rate"]
    results = {}
    for idx, segment in enumerate(segments):
        t0, t1 = segment_window(segments, idx, pre_sec, post_sec)
        lo, hi = int(round(t0 * sr)), int(round(t1 * sr))
        window_audio = np.zeros(hi - lo, dtype=np.float32)
        window_cov = np.zeros(hi - lo, dtype=bool)
        src_hi = min(hi, len(audio))
        if src_hi > lo:
            window_audio[:src_hi - lo] = audio[lo:src_hi]
            window_cov[:src_hi - lo] = covered[lo:src_hi]
        if not window_cov.any():
            continue  # o servidor também não pontua verso sem nenhum pacote
        rms = float(np.sqrt(np.mean(window_audio[window_cov] ** 2)))

        runs: dict = {}
        if segment_scoring.needs_whisper(segment, rms):
            text, words = stt.transcribe(window_audio, **segment_scoring.transcribe_kwargs(segment), details=runs)
            words = segment_scoring.shift_words(words, t0 - segment["sing_start"])
            prev = segments[idx - 1] if idx > 0 else None
            result = segment_scoring.score_words(segment, prev, words, scoring_mode)
            result.setdefault("transcription", text)
        else:
            result = segment_scoring.score_whisper_free(segment, rms)
        # "unprompted" = a dica foi recusada pelo portão de confiança e valeu a passada sem dica
        results[idx] = {**result, "rms": rms, "used": runs.get("used")}
    return results


def _cut(text: str, width: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width - 1] + "…"


def print_report(session_dir: Path, session: dict, player: str, replayed: dict[int, dict],
                 gabarito: dict[int, float]) -> dict:
    recorded = {r["segment"]: r for r in session["results"] if r["player"] == player}
    n_segments = len(session["segments"])
    print(f"\n=== {session_dir.name} · {player} · {session.get('song_title') or session['song_id']}"
          f"{'' if session.get('complete') else ' (INCOMPLETA)'}")
    header = f"{'#':>3} {'letra':<34} {'rms':>6} {'grav':>5} {'nova':>5}"
    if gabarito:
        header += f" {'esp':>5}"
    print(header + "  transcrição nova")
    for idx, segment in enumerate(session["segments"]):
        rec = recorded.get(idx, {}).get("score")
        new = replayed.get(idx)
        line = (f"{idx + 1:>3} {_cut(segment['lyrics'], 34):<34} "
                f"{(new['rms'] if new else 0):>6.3f} "
                f"{'-' if rec is None else f'{rec:.0f}':>5} "
                f"{'-' if new is None else f'{new['score']:.0f}':>5}")
        if gabarito:
            line += f" {'' if idx not in gabarito else f'{gabarito[idx]:.0f}':>5}"
        mark = "*" if new and new.get("used") == "unprompted" else " "
        print(line + " " + mark + _cut(new.get("transcription", "") if new else "", 50))

    # Nota final como no game_over: soma dos versos pontuados / total de versos.
    final_rec = sum(r["score"] for r in recorded.values()) / max(1, n_segments)
    final_new = sum(r["score"] for r in replayed.values()) / max(1, n_segments)
    summary = {"session": session_dir.name, "player": player, "final_recorded": round(final_rec, 1),
               "final_replay": round(final_new, 1)}
    retried = sum(1 for r in replayed.values() if r.get("used") == "unprompted")
    summary["unprompted"] = retried
    msg = f"Final: gravada {final_rec:.1f} · nova {final_new:.1f} · {retried} versos sem a dica (*)"
    if gabarito:
        errors = [abs(replayed.get(i, {"score": 0.0})["score"] - exp) for i, exp in gabarito.items()]
        summary["mae"] = round(sum(errors) / len(errors), 1)
        msg += f" · erro médio vs gabarito {summary['mae']:.1f} ({len(errors)} versos)"
    print(msg)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="Pasta da partida ou pasta com várias (padrão: karaoke/recordings)")
    parser.add_argument("--model", help="Modelo do faster-whisper (padrão: o do servidor)")
    parser.add_argument("--device", help="auto | cuda | cpu")
    parser.add_argument("--compute", help="compute_type do faster-whisper")
    parser.add_argument("--scoring-mode", choices=["timing", "words"], help="Padrão: o da partida")
    parser.add_argument("--pre", type=float, help="Pré-roll da janela em s (padrão: o da partida)")
    parser.add_argument("--post", type=float, help="Pós-roll da janela em s (padrão: o da partida)")
    parser.add_argument("--set", action="append", default=[], metavar="modulo.NOME=valor",
                        help="Troca uma constante antes de pontuar (repetível)")
    parser.add_argument("--json", type=Path, help="Salva o resumo em JSON (para comparar rodadas)")
    args = parser.parse_args()

    sessions = find_sessions(args.paths)
    apply_overrides(args.set)

    from stt_engine import STTEngine
    stt = STTEngine(model_size=args.model, device=args.device, compute_type=args.compute)

    summaries = []
    for session_dir in sessions:
        session = json.loads((session_dir / SESSION_FILE).read_text(encoding="utf-8"))
        windows = session.get("windows", {})
        pre = args.pre if args.pre is not None else windows.get("pre_sing_sec", 1.5)
        post = args.post if args.post is not None else windows.get("post_sing_sec", 0.5)
        for player, info in session["players"].items():
            audio = read_wav(session_dir / info["audio"])
            covered = covered_mask(info["covered"], len(audio), session["sample_rate"])
            replayed = replay_player(session, audio, covered, stt,
                                     args.scoring_mode or session["scoring_mode"], pre, post)
            summaries.append(print_report(session_dir, session, player, replayed,
                                          load_gabarito(session_dir, player)))

    if len(summaries) > 1:
        mean_new = sum(s["final_replay"] for s in summaries) / len(summaries)
        mean_rec = sum(s["final_recorded"] for s in summaries) / len(summaries)
        print(f"\nMédia das partidas: gravada {mean_rec:.1f} · nova {mean_new:.1f}")
    if args.json:
        args.json.write_text(json.dumps({"args": sys.argv[1:], "sessions": summaries}, ensure_ascii=False, indent=2),
                             encoding="utf-8")


if __name__ == "__main__":
    main()
