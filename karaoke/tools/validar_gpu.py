"""Validação no servidor com GPU: o que não deu para medir na máquina de desenvolvimento.

Cada comando é um item de "Validar no servidor" em docs/guides/TODO_SERVIDOR_FINAL.md.
Roda com o venv do servidor, de dentro de karaoke/, COM O SERVIDOR PARADO (o script
carrega o próprio Whisper e o MMS_FA na GPU; com o servidor ligado a VRAM estoura).

    python tools/validar_gpu.py ambiente
    python tools/validar_gpu.py baixar-modelo
    python tools/validar_gpu.py separacao server/songs/<slug>/original.mp3
    python tools/validar_gpu.py versoes
    python tools/validar_gpu.py musica server/songs/<slug>

Relatórios e áudios para ouvir em validacao_gpu/ (fora do git).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for p in (PROJECT_ROOT, PROJECT_ROOT / "server"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import utils.cuda_bootstrap  # noqa: E402,F401  (DLLs do CUDA no Windows antes do torch)
import torch  # noqa: E402,F401  (cuDNN 9.1 do torch antes do 9.10 do ctranslate2: na ordem inversa a 1ª conv na GPU derruba o processo)

OUT = PROJECT_ROOT / "validacao_gpu"
HOLIDAY = PROJECT_ROOT / "docs" / "archive" / "holiday-green-day"
SR = 16000


def _ffmpeg() -> str:
    try:
        from state import ffmpeg_bin_dir

        if ffmpeg_bin_dir:
            exe = Path(ffmpeg_bin_dir) / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
            if exe.exists():
                return str(exe)
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if not found:
        sys.exit("ffmpeg não encontrado")
    return found


def _run_ffmpeg(*args: str) -> None:
    subprocess.run([_ffmpeg(), "-v", "error", "-y", *args], check=True)


def _save(name: str, data) -> Path:
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


class VramPeak:
    """Pico de VRAM usada na placa (nvidia-smi a cada 0,5 s), inclusive de subprocessos."""

    def __init__(self):
        self.peak = None
        self._stop = threading.Event()

    def _read(self):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5).stdout
            return int(out.strip().splitlines()[0])
        except Exception:
            return None

    def _loop(self):
        while not self._stop.is_set():
            v = self._read()
            if v is not None:
                self.peak = max(self.peak or 0, v)
            self._stop.wait(0.5)

    def __enter__(self):
        self.base = self._read()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join()


# ---------------------------------------------------------------------------
# ambiente
# ---------------------------------------------------------------------------

def cmd_ambiente(_args) -> None:
    import importlib.metadata as md

    import torch

    report = {"python": sys.version.split()[0], "torch": torch.__version__, "cuda": torch.cuda.is_available()}
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        report.update(gpu=props.name, vram_gb=round(props.total_memory / 2**30, 1))
    pins = {}
    req = PROJECT_ROOT / "requirements.txt"
    for line in req.read_text(encoding="utf-8").splitlines():
        if "==" in line and not line.startswith("#"):
            name, ver = line.split("==", 1)
            pins[name.strip().lower()] = ver.strip()
    drift = {}
    for name in ("numpy", "onnxruntime", "torch", "torchaudio", "faster-whisper", "ctranslate2"):
        try:
            have = md.version(name)
        except md.PackageNotFoundError:
            continue
        want = pins.get(name)
        if want and have.split("+")[0] != want.split("+")[0]:
            drift[name] = {"requirements": want, "instalado": have}
    report["fora_do_requirements"] = drift
    from utils import separation

    report["audio_separator"] = separation.roformer_available()
    report["separador_auto"] = separation.separator_backend()
    report["roformer_modelo"] = separation.ROFORMER_MODEL
    model_file = Path(separation.ROFORMER_MODEL_DIR) / separation.ROFORMER_MODEL
    report["roformer_modelo_baixado"] = model_file.exists()
    report["whisper_modelo"] = os.environ.get("KARAOKE_WHISPER_MODEL", "large-v3-turbo")
    for k, v in report.items():
        print(f"{k:24s} {v}")
    if drift:
        print("\n▲ versões fora do requirements.txt: o audio-separator pode ter atualizado algo.")
    print(f"\nrelatório: {_save('ambiente', report)}")


def cmd_baixar_modelo(_args) -> None:
    """Baixa o modelo do RoFormer (~600 MB) fora do lock da GPU do servidor."""
    from utils import separation

    if not separation.roformer_available():
        sys.exit("audio-separator não instalado: pip install audio-separator==0.47.0")
    from audio_separator.separator import Separator

    Path(separation.ROFORMER_MODEL_DIR).mkdir(parents=True, exist_ok=True)
    sep = Separator(model_file_dir=separation.ROFORMER_MODEL_DIR, output_dir=str(OUT))
    sep.load_model(model_filename=separation.ROFORMER_MODEL)
    print(f"modelo pronto em {separation.ROFORMER_MODEL_DIR}")


# ---------------------------------------------------------------------------
# separacao: RoFormer × Demucs no mesmo áudio
# ---------------------------------------------------------------------------

def cmd_separacao(args) -> None:
    from utils import separation

    src = Path(args.audio).resolve()
    if not src.exists():
        sys.exit(f"não achei {src}")
    if args.com_whisper:
        # o servidor deixa o Whisper carregado: a separação divide a VRAM com ele
        from stt_engine import get_stt_engine

        get_stt_engine()
        print("Whisper carregado (como no servidor)")
    work = OUT / f"separacao-{src.stem}"
    work.mkdir(parents=True, exist_ok=True)
    report = {"audio": str(src)}
    for backend in ("roformer", "demucs"):
        if backend == "roformer" and not separation.roformer_available():
            print("RoFormer: audio-separator não instalado, pulando")
            continue
        out = work / backend
        t = time.time()
        with VramPeak() as vram:
            try:
                fn = separation._separate_roformer if backend == "roformer" else separation._separate_demucs
                vocals, inst = fn(src, out, separation._best_device())
                ok = True
            except Exception as e:
                ok, vocals, inst = False, None, None
                print(f"{backend}: FALHOU {e}")
        secs = round(time.time() - t, 1)
        row = {"ok": ok, "segundos": secs, "vram_base_mb": vram.base, "vram_pico_mb": vram.peak}
        if ok:
            for stem, path in (("voz", vocals), ("instrumental", inst)):
                dst = work / f"{backend}-{stem}.wav"
                shutil.copy(path, dst)
                row[stem] = str(dst)
        report[backend] = row
        print(f"{backend:9s} {secs:7.1f}s  VRAM pico {vram.peak} MB (antes {vram.base} MB)")
    print(f"\nouvir: {work}  (compare *-instrumental.wav: voz vazando, pratos, reverb)")
    print(f"relatório: {_save('separacao-' + src.stem, report)}")


# ---------------------------------------------------------------------------
# versoes: Holiday em versões simuladas (o mesmo teste feito em CPU)
# ---------------------------------------------------------------------------

def _variants(vocal: Path, work: Path) -> dict:
    """Versões simuladas do stem e a função tempo-de-estúdio → tempo-da-versão (None = cortado)."""
    orig = work / "orig.wav"
    _run_ffmpeg("-i", str(vocal), "-ac", "1", "-ar", str(SR), str(orig))
    _run_ffmpeg("-i", str(orig), "-af", "adelay=8000", str(work / "intro8.wav"))
    _run_ffmpeg("-i", str(orig), "-af", "atempo=0.97", str(work / "slow3.wav"))
    _run_ffmpeg("-ss", "5", "-i", str(orig), "-af", "atempo=1.03", str(work / "cut5fast3.wav"))
    _run_ffmpeg("-i", str(orig), "-filter_complex",
                "[0]atrim=0:107.5,asetpts=N/SR/TB[a];[0]atrim=45.5:66.5,asetpts=N/SR/TB[b];"
                "[0]atrim=107.5,asetpts=N/SR/TB[c];[a][b][c]concat=n=3:v=0:a=1", str(work / "extrachorus.wav"))
    _run_ffmpeg("-i", str(orig), "-filter_complex",
                "[0]atrim=0:66.8,asetpts=N/SR/TB[a];[0]atrim=92.9,asetpts=N/SR/TB[c];"
                "[a][c]concat=n=2:v=0:a=1", str(work / "cutverse.wav"))

    def expected(name, ref):
        if name == "intro8":
            return [(x, t + 8) for x, t in ref]
        if name == "slow3":
            return [(x, t / 0.97) for x, t in ref]
        if name == "cut5fast3":
            return [(x, (t - 5) / 1.03) for x, t in ref if t >= 5]
        if name == "extrachorus":
            return ([(x, t) for x, t in ref if t < 107.5] + [(x, t + 62) for x, t in ref if 45.5 <= t < 66.5]
                    + [(x, t + 21) for x, t in ref if t >= 107.5])
        if name == "cutverse":
            return [(x, t) for x, t in ref if t < 66.8] + [(x, t - 26.1) for x, t in ref if t >= 92.9]
        return list(ref)
    return expected


def _score_lines(got: list[tuple[str, float]], want: list[tuple[str, float]], tol: float = 3.0) -> dict:
    import numpy as np

    pool, errs = list(got), []
    for text, t in want:
        cands = [g for g in pool if g[0].lower().strip() == text.lower().strip()]
        g = min(cands, key=lambda g: abs(g[1] - t)) if cands else None
        if g is None or abs(g[1] - t) > tol:
            continue
        pool.remove(g)
        errs.append(abs(g[1] - t))
    return {"ok": len(errs), "esperadas": len(want), "sobra": len(pool),
            "mediana_s": round(float(np.median(errs)), 2) if errs else None}


def _whisper_words(audio, language: str = "en"):
    from stt_engine import get_stt_engine
    from utils.whisper_params import TRANSCRIBE_KWARGS

    segs, _ = get_stt_engine().model.transcribe(audio, language=language, **TRANSCRIBE_KWARGS)
    return [{"word": w.word.strip(), "start": float(w.start), "end": float(w.end), "probability": float(w.probability)}
            for s in segs for w in (s.words or [])]


def cmd_versoes(args) -> None:
    from utils.audio import load_audio_full
    from utils.lrc_pro import align_lyrics_forced, parse_synced_lrc
    from utils.lrc_sync import sync_lrc
    from utils.lyrics_fetcher import fetch_lyrics

    vocal = HOLIDAY / "vocal.mp3"
    if not vocal.exists():
        sys.exit(f"não achei {vocal}")
    work = OUT / "versoes"
    work.mkdir(parents=True, exist_ok=True)
    fetched = fetch_lyrics("Green Day", "Holiday", duration=232.9)
    if not fetched or not fetched.get("syncedLyrics"):
        sys.exit("LRCLIB sem LRC sincronizado para Holiday (sem internet?)")
    lrc, plain = fetched["syncedLyrics"], fetched["plainLyrics"]
    ref = [(ln["text"], ln["start"]) for ln in parse_synced_lrc(lrc)]
    expected = _variants(vocal, work)
    cases = args.casos.split(",")
    report = {}
    print(f"{'versão':12s} {'modo':16s} {'linhas ok':>10s} {'sobra':>6s} {'mediana':>8s} {'tempo':>7s}")
    for name in cases:
        wav = work / f"{name}.wav"
        audio = load_audio_full(str(wav))
        t = time.time()
        words = _whisper_words(audio)
        whisper_s = round(time.time() - t, 1)
        want = expected(name, ref)
        rows = {}
        # modo rápido: só o LRC escolhido (sem MMS_FA)
        t = time.time()
        res = sync_lrc(lrc, plain, audio, "en", words=words)
        got = [(ln["text"], ln["start"]) for ln in parse_synced_lrc(res.lrc_text or "")]
        rows["rapido_antes"] = {**_score_lines([(x, t0) for x, t0 in ref], want), "segundos": 0}
        rows["rapido_agora"] = {**_score_lines(got, want), "metodo": res.method, "segundos": round(time.time() - t, 1)}
        if not args.sem_pro:
            for label, fn in (("pro_antes", None), ("pro_agora", lambda a: words)):
                t = time.time()
                segs, _ = align_lyrics_forced(str(wav), plain, "en", synced_lrc=lrc, transcribe_fn=fn)
                got = [(s["lyrics"], s["sing_start"] + s["lyrics_timed"][0]["expected_start"])
                       for s in segs if s.get("lyrics_timed")]
                rows[label] = {**_score_lines(got, want), "segundos": round(time.time() - t, 1)}
        rows["whisper_segundos"] = whisper_s
        report[name] = rows
        for mode, r in rows.items():
            if isinstance(r, dict):
                print(f"{name:12s} {mode:16s} {r['ok']:>4d}/{r['esperadas']:<5d} {r['sobra']:>6d} "
                      f"{str(r['mediana_s']):>8s} {r['segundos']:>6}s")
        print(f"{name:12s} {'whisper do stem':16s} {'':>10s} {'':>6s} {'':>8s} {whisper_s:>6}s")
    print(f"\nesperado (CPU, 2026-10-01): PRO agora 39/39 em orig/intro8/slow3, 39/42 no extrachorus;"
          f" cutverse sem as 6 linhas do verso 2")
    print(f"relatório: {_save('versoes', report)}")


# ---------------------------------------------------------------------------
# musica: o que o sistema faria com uma música real instalada (sem gravar nada nela)
# ---------------------------------------------------------------------------

def cmd_musica(args) -> None:
    from utils.audio import load_audio_full
    from utils.lrc_pro import parse_synced_lrc
    from utils.lrc_sync import sync_lrc
    from utils.lyrics_fetcher import fetch_lyrics

    song = Path(args.pasta).resolve()
    meta = json.loads((song / "meta.json").read_text(encoding="utf-8"))
    artist, title = meta["meta"].get("artist"), meta["meta"].get("title")
    lang = meta["meta"].get("language") or "pt"
    audio = load_audio_full(str(song / "vocal.mp3"))
    duration = len(audio) / SR
    print(f"{artist} — {title}: vocal de {duration:.1f}s, idioma {lang}")
    fetched = fetch_lyrics(artist, title, duration=duration) or {}
    print(f"LRCLIB: versão de {fetched.get('duration')}s, LRC sincronizado: {bool(fetched.get('syncedLyrics'))}")
    current = (song / "lyrics.lrc").read_text(encoding="utf-8") if (song / "lyrics.lrc").exists() else None
    lrc = fetched.get("syncedLyrics") or current
    plain = fetched.get("plainLyrics") or (meta.get("lyrics") or {}).get("plain_lyrics")
    t = time.time()
    words = _whisper_words(audio, lang)
    whisper_s = time.time() - t
    res = sync_lrc(lrc, plain, audio, lang, words=words)
    print(f"Whisper do stem: {whisper_s:.1f}s")
    if res.fit:
        print(f"encaixe: escala {res.fit.scale} offset {res.fit.offset:+.2f}s F1 {res.fit.f1_before} → {res.fit.f1}"
              f" ({'aplicado' if res.fit.applied else 'mantido'})")
    if res.plan:
        p = res.plan
        print(f"estrutura: {len(p.anchors)} linhas, {sum(a.kind == 'repeat' for a in p.anchors)} repetidas, "
              f"fora {[i + 1 for i in p.dropped]}, {100 * p.coverage:.0f}% das palavras casadas")
    print(f"concordância LRC × estrutura: {res.agreement}  →  método escolhido: {res.method}")
    if res.lrc_text:
        preview = OUT / f"{song.name}.sync_preview.lrc"
        OUT.mkdir(exist_ok=True)
        preview.write_text(res.lrc_text, encoding="utf-8")
        moved = 0
        if current:
            old = {ln["text"]: ln["start"] for ln in parse_synced_lrc(current)}
            moved = sum(1 for ln in parse_synced_lrc(res.lrc_text) if ln["text"] in old and abs(old[ln["text"]] - ln["start"]) > 1.0)
        print(f"LRC proposto: {preview}  ({moved} linhas a mais de 1 s do lyrics.lrc atual)")
        print("Toque a música com ele no editor de letra para conferir; o lyrics.lrc da pasta não foi mexido.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ambiente", help="GPU, versões e o que está instalado").set_defaults(fn=cmd_ambiente)
    sub.add_parser("baixar-modelo", help="baixa o modelo do RoFormer").set_defaults(fn=cmd_baixar_modelo)
    s = sub.add_parser("separacao", help="RoFormer × Demucs no mesmo áudio (tempo, VRAM, arquivos para ouvir)")
    s.add_argument("audio")
    s.add_argument("--com-whisper", action="store_true", help="carrega o Whisper antes, como no servidor")
    s.set_defaults(fn=cmd_separacao)
    v = sub.add_parser("versoes", help="Holiday em versões simuladas: modo rápido e PRO, antes × agora")
    v.add_argument("--casos", default="orig,intro8,slow3,cut5fast3,extrachorus,cutverse")
    v.add_argument("--sem-pro", action="store_true", help="só o modo rápido (sem MMS_FA)")
    v.set_defaults(fn=cmd_versoes)
    m = sub.add_parser("musica", help="o LRC que o sistema escolheria para uma música instalada")
    m.add_argument("pasta")
    m.set_defaults(fn=cmd_musica)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
