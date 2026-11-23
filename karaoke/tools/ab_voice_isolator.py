"""A/B do Inworld Voice Isolator no alinhamento da letra (MMS_FA).

Pergunta: passar o stem de voz (vocal.mp3) pelo isolador antes do alinhamento
deixa a letra mais no tempo? Para cada música, alinha DUAS vezes com a mesma
letra e os mesmos inícios de linha (lyrics.lrc atual):

    A = stem como está hoje
    B = stem limpo pelo isolador (voice-isolator-v1, offline, 48 kHz)

e compara a nota do `alignment_quality.assess`. Os dois lados são julgados
contra a MESMA referência (RMS e Whisper do stem original), então a diferença
vem só do alinhamento. Nada na pasta da música é alterado.

Roda no servidor com GPU, com o venv do servidor, de dentro de karaoke/, COM O
SERVIDOR PARADO (MMS_FA e isolador na GPU; com o servidor ligado a VRAM estoura).

    pip install inworld-voice-isolation          # uma vez (opcional: "[fast]")
    python tools/ab_voice_isolator.py --piores 10 --melhores 5
    python tools/ab_voice_isolator.py morgana-kamaitachi wave-paula-sergio
    python tools/ab_voice_isolator.py --piores 10 --estrutura   # + plano por estrutura (Whisper)

Saída em ab_isolador/<data-hora>/ (fora do git): relatorio.md, relatorio.json e,
por música, vocal_isolado.wav (para ouvir), segments_A.json e segments_B.json.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "server"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SONGS_DIR = PROJECT_ROOT / "server" / "songs"
OUT_ROOT = PROJECT_ROOT / "ab_isolador"
ISOLATOR_SR = 48000
# {entrada} e {saida} são trocados pelos caminhos dos WAVs
DEFAULT_ISOLATOR_CMD = "voice-isolate {entrada} {saida}"


# ---------------------------------------------------------------- seleção (sem GPU)

def song_score(song_dir: Path) -> float | None:
    try:
        meta = json.loads((song_dir / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    q = meta.get("alignment_quality") or {}
    return q.get("score")


def pick_songs(songs_dir: Path, slugs: list[str], worst: int, best: int) -> list[str]:
    """Slugs pedidos + as `worst` de menor nota + as `best` de maior (controle).

    Só entram músicas com vocal.mp3 e letra (a de controle mostra se o isolador piora
    o que já estava bom). Ordem: pedidas, piores, melhores; sem repetir.
    """
    ranked = []
    for d in sorted(p for p in songs_dir.iterdir() if p.is_dir()):
        score = song_score(d)
        if score is not None and (d / "vocal.mp3").exists():
            ranked.append((score, d.name))
    ranked.sort()
    chosen = list(slugs)
    chosen += [s for _, s in ranked[:worst]]
    chosen += [s for _, s in reversed(ranked[-best:])] if best else []
    seen, out = set(), []
    for s in chosen:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def summarize(quality: dict) -> dict:
    """Resumo comparável de um `assess`: nota, versos graves e contagem das marcações por verso."""
    flags = Counter(f for ln in quality.get("lines") or [] for f in ln.get("flags") or [])
    return {
        "score": quality.get("score"),
        "severe": len(quality.get("severe_lines") or []),
        "lines": len(quality.get("lines") or []),
        "line_flags": dict(flags),
        "flags": quality.get("flags") or [],
    }


def verdict(a: dict, b: dict, margin: float = 2.0) -> str:
    """'melhor' | 'pior' | 'igual' pela nota (margem contra ruído) e versos graves."""
    ds = (b["score"] or 0) - (a["score"] or 0)
    dg = b["severe"] - a["severe"]
    if ds >= margin and dg <= 0 or ds > -margin and dg < 0:
        return "melhor"
    if ds <= -margin and dg >= 0 or ds < margin and dg > 0:
        return "pior"
    return "igual"


# ---------------------------------------------------------------- GPU

def to_wav(src: Path, dst: Path, rate: int) -> None:
    """Qualquer áudio → WAV mono float32 em `rate` (PyAV, já é dependência)."""
    import av
    import numpy as np
    import soundfile as sf

    container = av.open(str(src))
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=rate)
    chunks = []
    for frame in container.decode(container.streams.audio[0]):
        chunks += [f.to_ndarray().flatten() for f in resampler.resample(frame)]
    chunks += [f.to_ndarray().flatten() for f in resampler.resample(None)]
    container.close()
    sf.write(str(dst), np.concatenate(chunks).astype("float32"), rate, subtype="FLOAT")


def isolate(vocal: Path, work: Path, cmd_template: str) -> tuple[Path, float]:
    """Roda o isolador (subprocesso: a VRAM dele volta ao sistema no fim). Devolve (wav, segundos)."""
    entrada = work / "vocal_48k.wav"
    saida = work / "vocal_isolado.wav"
    to_wav(vocal, entrada, ISOLATOR_SR)
    cmd = [part.format(entrada=str(entrada), saida=str(saida)) for part in shlex.split(cmd_template)]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    secs = time.time() - t0
    if proc.returncode != 0 or not saida.exists():
        tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-8:])
        raise RuntimeError(f"isolador falhou ({proc.returncode}): {tail}")
    entrada.unlink(missing_ok=True)
    return saida, secs


def align(vocal_path: Path, plain: str, language: str, synced_lrc: str | None, transcribe_fn):
    from utils.lrc_pro import align_lyrics_forced

    segments, _lrc = align_lyrics_forced(str(vocal_path), plain, language=language,
                                         synced_lrc=synced_lrc, transcribe_fn=transcribe_fn)
    return segments


def run_song(slug: str, out_dir: Path, cmd_template: str, use_structure: bool) -> dict:
    from utils.alignment_quality import assess, load_stem_words, rms_frames
    from utils.audio import load_audio_full

    song_dir = SONGS_DIR / slug
    meta = json.loads((song_dir / "meta.json").read_text(encoding="utf-8"))
    plain = ((meta.get("lyrics") or {}).get("plain_lyrics") or "").strip()
    language = (meta.get("meta") or {}).get("language") or "pt"
    vocal = song_dir / "vocal.mp3"
    if not plain or not vocal.exists():
        return {"slug": slug, "erro": "sem letra ou sem vocal.mp3"}
    lrc_path = song_dir / "lyrics.lrc"
    synced = lrc_path.read_text(encoding="utf-8") if lrc_path.exists() else None

    work = out_dir / slug
    work.mkdir(parents=True, exist_ok=True)

    # referência comum aos dois lados: RMS e Whisper do stem ORIGINAL
    original = load_audio_full(vocal)
    duration = len(original) / 16000
    ref_rms = rms_frames(original, 16000)
    ref_words = load_stem_words(song_dir)

    def transcriber():
        if not use_structure:
            return None
        from tools.reinstall_song import _structure_transcriber
        return _structure_transcriber(language, song_dir=None)  # sem cache: cada stem o seu

    result = {"slug": slug, "language": language, "lrc_inicial": synced is not None,
              "editada": (song_dir / ".lyrics_edited").exists(), "antes_no_meta": song_score(song_dir)}
    sides = {}
    for side, path in (("A", vocal), ("B", None)):
        try:
            t0 = time.time()
            if side == "B":
                path, iso_secs = isolate(vocal, work, cmd_template)
                result["isolador_s"] = round(iso_secs, 1)
            segs = align(path, plain, language, synced, transcriber())
            (work / f"segments_{side}.json").write_text(json.dumps(segs, indent=2, ensure_ascii=False),
                                                        encoding="utf-8")
            sides[side] = summarize(assess(segs, duration, ref_rms, stem_words=ref_words))
            sides[side]["tempo_s"] = round(time.time() - t0, 1)
        except Exception as e:
            sides[side] = {"erro": str(e)}
    result.update(sides)
    if "score" in sides.get("A", {}) and "score" in sides.get("B", {}):
        result["veredito"] = verdict(sides["A"], sides["B"])
        result["delta"] = round(sides["B"]["score"] - sides["A"]["score"], 1)
    return result


# ---------------------------------------------------------------- relatório

def report_md(results: list[dict], args) -> str:
    lines = [f"# A/B voice isolator · {datetime.now():%Y-%m-%d %H:%M}", "",
             f"isolador: `{args.isolador_cmd}` · estrutura: {'sim' if args.estrutura else 'não'}", "",
             "| música | A | B | Δ | graves A→B | veredito | isolador |",
             "|---|---:|---:|---:|---|---|---:|"]
    for r in results:
        a, b = r.get("A") or {}, r.get("B") or {}
        if "score" not in a or "score" not in b:
            err = r.get("erro") or a.get("erro") or b.get("erro")
            lines.append(f"| {r['slug']} | | | | | erro: {err} | |")
            continue
        lines.append(f"| {r['slug']} | {a['score']} | {b['score']} | {r['delta']:+} | "
                     f"{a['severe']}→{b['severe']} | {r['veredito']} | {r.get('isolador_s', '')} s |")
    ok = [r for r in results if "veredito" in r]
    if ok:
        c = Counter(r["veredito"] for r in ok)
        mean = sum(r["delta"] for r in ok) / len(ok)
        lines += ["", f"melhor {c['melhor']} · igual {c['igual']} · pior {c['pior']} · Δ médio {mean:+.1f}"]
        flags_a = Counter()
        flags_b = Counter()
        for r in ok:
            flags_a.update(r["A"]["line_flags"])
            flags_b.update(r["B"]["line_flags"])
        lines += ["", "| marcação por verso | A | B |", "|---|---:|---:|"]
        for f in sorted(set(flags_a) | set(flags_b), key=lambda f: -flags_a[f]):
            lines.append(f"| {f} | {flags_a[f]} | {flags_b[f]} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*", help="músicas (pastas em server/songs)")
    ap.add_argument("--piores", type=int, default=0, help="inclui as N de menor nota de alinhamento")
    ap.add_argument("--melhores", type=int, default=0, help="inclui as N de maior nota (controle)")
    ap.add_argument("--estrutura", action="store_true",
                    help="liga o plano por estrutura (Whisper de cada stem), como no reinstall")
    ap.add_argument("--isolador-cmd", default=DEFAULT_ISOLATOR_CMD,
                    help=f"comando do isolador com {{entrada}} e {{saida}} (padrão: {DEFAULT_ISOLATOR_CMD!r})")
    args = ap.parse_args()

    slugs = pick_songs(SONGS_DIR, args.slugs, args.piores, args.melhores)
    if not slugs:
        ap.error("nenhuma música: passe slugs ou --piores/--melhores")
    out_dir = OUT_ROOT / f"{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{len(slugs)} música(s) → {out_dir}")

    results = []
    for i, slug in enumerate(slugs, 1):
        print(f"[{i}/{len(slugs)}] {slug} ...", flush=True)
        r = run_song(slug, out_dir, args.isolador_cmd, args.estrutura)
        results.append(r)
        if "veredito" in r:
            print(f"    A {r['A']['score']} · B {r['B']['score']} ({r['delta']:+}) · {r['veredito']}")
        else:
            print(f"    erro: {r.get('erro') or (r.get('A') or {}).get('erro') or (r.get('B') or {}).get('erro')}")
        (out_dir / "relatorio.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    md = report_md(results, args)
    (out_dir / "relatorio.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    main()
