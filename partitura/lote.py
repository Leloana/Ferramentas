"""Teste em massa do modo leve (sem LLM): centenas de músicas, GPU pro AMT-APC, CPU em paralelo pro resto.

    python lote.py lista                                             # lista.txt: vídeos de origem do karaokê + buscas.txt
    python lote.py baixar     [--trabalhadores 6]                    # música integral do YouTube (wav 44,1 kHz mono)
    python lote.py preparar   --fonte pasta                          # (opcional) converte áudios integrais de uma pasta
    python lote.py amtapc                                            # AMT-APC de todas, modelo carregado 1 vez (GPU)
    python lote.py gerar      [--trabalhadores 12] [--reusar-cache]  # modo leve até o MusicXML (sem PDF nem prévia)
    python lote.py biblioteca [--trabalhadores 10]                   # PDF + prévia + original de todas, pro site:
                                                                     #   PARTITURA_SAIDA=trabalho/lote/biblioteca python run.py --lan --porta=8031
    python lote.py medir      [--trabalhadores 14] [--nome rodada]   # métricas por partitura -> <lote>/medidas_<nome>.json
    python lote.py resumo     [--nome rodada] [--contra outra]       # agregados (média, p50, p90) e comparação

Tudo fica em trabalho/lote/ (fora do git): audio/<slug>.wav, saida/<slug>/ (cache + editaveis/*.musicxml).
O `gerar` chama o próprio `gerar.main` (mesmo código do site), trocando só PDF, prévia e Original.mp3 por nada.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

AQUI = Path(__file__).resolve().parent
LOTE = AQUI / "trabalho" / "lote"
KARAOKE = AQUI.parent / "karaoke" / "server" / "songs"
NIVEIS = ("Facil", "Medio", "Dificil")


def _um_thread():
    for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ[v] = "1"


# ------------------------------------------------------------------ preparar

def _converter(origem: str, destino: str):
    import subprocess
    destino = Path(destino)
    if destino.exists():
        return destino.name, "já existe"
    tmp = destino.with_suffix(".tmp.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", origem, "-ac", "1", "-ar", "44100",
                    "-sample_fmt", "s16", str(tmp)], check=True)
    tmp.replace(destino)
    return destino.name, "ok"


def preparar(a):
    _um_thread()
    pasta_audio = LOTE / "audio"
    pasta_audio.mkdir(parents=True, exist_ok=True)
    tarefas = []
    if not a.fonte or not Path(a.fonte).is_dir():
        raise SystemExit("--fonte <pasta com áudios integrais> (nunca faixas separadas pelo Demucs)")
    for p in sorted(Path(a.fonte).rglob("*")):
        if p.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".webm"):
            tarefas.append((_converter, str(p), str(pasta_audio / f"{_slug(p.stem)}.wav")))
    if a.limite:
        tarefas = tarefas[:a.limite]
    print(f"{len(tarefas)} músicas")
    with ProcessPoolExecutor(a.trabalhadores) as ex:
        fut = [ex.submit(f, *args) for f, *args in tarefas]
        for i, f in enumerate(as_completed(fut), 1):
            try:
                nome, info = f.result()
                print(f"[{i}/{len(fut)}] {nome}: {info}", flush=True)
            except Exception as e:
                print(f"[{i}/{len(fut)}] ERRO {e}", flush=True)


# ------------------------------------------------------------------ música integral do YouTube

def _slug(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:70] or "sem-nome"


def lista(a):
    """lista.txt (slug<TAB>alvo): o vídeo de origem de cada música do karaokê (a gravação inteira,
    não as faixas separadas) + uma busca do YouTube por linha de buscas.txt ("artista - música")."""
    linhas, vistos = [], set()
    for p in sorted(KARAOKE.iterdir()):
        try:
            m = json.loads((p / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        url = (m.get("audio") or {}).get("youtube_vocal_url")
        if url and p.name not in vistos:
            vistos.add(p.name)
            linhas.append(f"{p.name}\t{url}")
    buscas = LOTE / "buscas.txt"
    if buscas.exists():
        for q in buscas.read_text(encoding="utf-8").splitlines():
            q = q.strip()
            if q and not q.startswith("#") and _slug(q) not in vistos:
                vistos.add(_slug(q))
                linhas.append(f"{_slug(q)}\tytsearch1:{q} audio")
    (LOTE / "lista.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"{len(linhas)} músicas em {LOTE / 'lista.txt'}")


def _baixar_um(slug: str, alvo: str):
    import subprocess
    destino = LOTE / "audio" / f"{slug}.wav"
    if destino.exists():
        return slug, "já existe"
    tmp = LOTE / "baixando" / slug
    tmp.mkdir(parents=True, exist_ok=True)
    yt = AQUI / "venv" / "Scripts" / "yt-dlp.exe"
    r = subprocess.run([str(yt) if yt.exists() else "yt-dlp", "-q", "--no-warnings", "--no-playlist",
                        "-f", "bestaudio/best", "--match-filter", "duration >= 60 & duration <= 600",
                        "-o", str(tmp / "a.%(ext)s"), "--print-to-file", "%(title)s | %(duration)s s | %(webpage_url)s",
                        str(tmp / "info.txt"), alvo], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    arqs = [p for p in tmp.glob("a.*") if not p.name.endswith(".part")]
    if not arqs:
        return slug, f"falhou: {(r.stderr or 'sem arquivo (duração fora de 1-10 min?)').strip()[:150]}"
    wav_tmp = destino.with_suffix(".tmp.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(arqs[0]), "-ac", "1", "-ar", "44100",
                    "-sample_fmt", "s16", str(wav_tmp)], check=True, stdin=subprocess.DEVNULL)
    wav_tmp.replace(destino)
    info = (tmp / "info.txt").read_text(encoding="utf-8", errors="replace").strip() if (tmp / "info.txt").exists() else ""
    (LOTE / "audio" / f"{slug}.txt").write_text(info, encoding="utf-8")
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    return slug, info


def baixar(a):
    (LOTE / "audio").mkdir(parents=True, exist_ok=True)
    itens = [l.split("\t", 1) for l in (LOTE / "lista.txt").read_text(encoding="utf-8").splitlines() if "\t" in l]
    if a.limite:
        itens = itens[:a.limite]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(a.trabalhadores) as ex:
        fut = [ex.submit(_baixar_um, s, u) for s, u in itens]
        for i, f in enumerate(as_completed(fut), 1):
            try:
                s, info = f.result()
            except Exception as e:
                s, info = "?", f"ERRO {e}"
            print(f"[{i}/{len(fut)}] {s}: {info}", flush=True)


# ------------------------------------------------------------------ AMT-APC em lote (GPU)

def amtapc(a):
    """Carrega o modelo uma vez e gera <saida>/<slug>/cache/amtapc_medio.mid de cada música."""
    repo = AQUI / "modelos" / "amt-apc"
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    import torch
    import torchaudio
    try:
        import torchcodec  # noqa: F401
    except Exception:
        import soundfile

        def _ler(caminho, *_, **__):
            dados, sr = soundfile.read(str(caminho), dtype="float32", always_2d=True)
            return torch.from_numpy(dados.T.copy()), sr
        torchaudio.load = _ler
    from models import Pipeline
    from data import SVSampler
    from utils import config
    pipe = Pipeline(config.path.apc, torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    sv = SVSampler().sample(params="level2")   # variâncias 0: mesmo vetor de estilo do amtapc.py
    audios = sorted((LOTE / "audio").glob("*.wav"))
    audios = [p for p in audios if not p.name.endswith(".tmp.wav")]
    t0, feitos = time.time(), 0
    for i, wav in enumerate(audios, 1):
        destino = LOTE / "saida" / wav.stem / "cache" / "amtapc_medio.mid"
        if destino.exists():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp = destino.with_suffix(".tmp.mid")
            with torch.no_grad():
                pipe.wav2midi(str(wav), str(tmp), sv, silent=True)
            tmp.replace(destino)
            feitos += 1
            print(f"[{i}/{len(audios)}] {wav.stem} ({(time.time() - t0) / feitos:.1f} s/música)", flush=True)
        except Exception as e:
            print(f"[{i}/{len(audios)}] ERRO {wav.stem}: {e}", flush=True)


# ------------------------------------------------------------------ modo leve até o MusicXML

def aplicar_ajustes(ajustes: dict):
    """{"modulo.CONSTANTE": v} troca a constante; {"modulo.funcao.arg": v} troca o padrão do argumento
    (a função é embrulhada no próprio módulo, então quem a chama pelo nome global pega o novo padrão)."""
    import functools
    import importlib
    por_funcao = {}
    for chave, v in ajustes.items():
        partes = chave.split(".")
        mod = importlib.import_module(partes[0])
        if len(partes) == 2:
            atual = getattr(mod, partes[1])
            if isinstance(atual, dict) and isinstance(v, dict):
                v = {**atual, **{k: ({**atual[k], **x} if isinstance(atual.get(k), dict) and isinstance(x, dict) else x)
                                 for k, x in v.items()}}
            setattr(mod, partes[1], v)
        else:
            por_funcao.setdefault((partes[0], partes[1]), {})[partes[2]] = v
    for (m, f), kw in por_funcao.items():
        mod = importlib.import_module(m)
        orig = getattr(mod, f)
        setattr(mod, f, functools.wraps(orig)(functools.partial(orig, **kw)))


def _gerar_um(wav: str, saida: str, extra: list[str], ajustes: dict | None = None):
    _um_thread()
    import io
    import contextlib
    wav = Path(wav)
    log = LOTE / "logs" / Path(saida).name / f"{wav.stem}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(AQUI))
    import gerar
    if ajustes:
        aplicar_ajustes(ajustes)
    gerar.xml_para_pdf = lambda xml, pdf: 0
    gerar.midi_para_mp3 = lambda mid, mp3: None
    gerar.renderizar_previas_pendentes = lambda *a, **k: None
    gerar.copiar_original = lambda audio, pasta: Path(pasta).mkdir(parents=True, exist_ok=True)
    gerar.salvar_midi_notas = lambda *a, **k: None
    sys.argv = ["gerar.py", str(wav), "--leve", "--nivel", "todos", "--saida", saida, "--pasta", wav.stem,
                "--titulo", wav.stem, *extra]
    t0 = time.time()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            gerar.main()
        ok = True
    except BaseException:
        buf.write(traceback.format_exc())
        ok = False
    log.write_text(buf.getvalue(), encoding="utf-8")
    return wav.stem, ok, time.time() - t0


def gerar_lote(a):
    audios = sorted(p for p in (LOTE / "audio").glob("*.wav") if not p.name.endswith(".tmp.wav"))
    if a.musicas:
        quer = set(a.musicas.split(","))
        audios = [p for p in audios if p.stem in quer]
    if a.lista:   # medidas_<nome>.json (as músicas medidas nela) ou .txt (uma por linha)
        arq = LOTE / a.lista
        quer = set(json.loads(arq.read_text(encoding="utf-8"))) if arq.suffix == ".json" else             set(arq.read_text(encoding="utf-8").split())
        audios = [p for p in audios if p.stem in quer]
    # só quem já tem o arranjo da IA (senão cada processo carregaria o AMT-APC sozinho na GPU)
    audios = [p for p in audios if (LOTE / "saida" / p.stem / "cache" / "amtapc_medio.mid").exists()]
    saida = str(LOTE / (a.saida or "saida"))
    if a.pular_prontos:
        audios = [p for p in audios if not (Path(saida) / p.stem / "editaveis" / "AMT-APC - Dificil.musicxml").exists()]
    if a.limite:
        audios = audios[:a.limite]
    extra = (["--reusar-cache"] if a.reusar_cache else []) + (a.extra.split() if a.extra else [])
    # cache do AMT-APC e das batidas fica na pasta "saida"; outra saída copia o cache antes
    if a.saida and a.saida != "saida":
        import shutil
        for p in audios:
            orig, dest = LOTE / "saida" / p.stem / "cache", Path(saida) / p.stem / "cache"
            if orig.exists() and not dest.exists():
                shutil.copytree(orig, dest, ignore=shutil.ignore_patterns("sincronia_original.json"))
    t0, erros = time.time(), []
    with ProcessPoolExecutor(a.trabalhadores) as ex:
        fut = {ex.submit(_gerar_um, str(p), saida, extra, json.loads(a.ajustes) if a.ajustes else None): p for p in audios}
        for i, f in enumerate(as_completed(fut), 1):
            nome, ok, dt = f.result()
            if not ok:
                erros.append(nome)
            print(f"[{i}/{len(fut)}] {'ok  ' if ok else 'ERRO'} {nome} {dt:.0f} s "
                  f"(total {(time.time() - t0) / 60:.1f} min)", flush=True)
    print(f"{len(audios) - len(erros)} ok, {len(erros)} com erro: {erros[:20]}")


# ------------------------------------------------------------------ biblioteca pro site (PDF + prévia)

def _info_musica(slug: str) -> dict:
    """titulo, artista e video_id: do meta.json do karaokê ou da busca "Artista - Música"."""
    info = {}
    kar = KARAOKE / slug / "meta.json"
    if kar.exists():
        m = json.loads(kar.read_text(encoding="utf-8"))
        info = dict(titulo=m.get("meta", {}).get("title"), artista=m.get("meta", {}).get("artist"))
    else:
        for linha in (LOTE / "buscas.txt").read_text(encoding="utf-8").splitlines():
            if linha.strip() and not linha.startswith("#") and _slug(linha) == slug and " - " in linha:
                artista, titulo = linha.split(" - ", 1)
                info = dict(titulo=titulo.strip(), artista=artista.strip())
    txt = LOTE / "audio" / f"{slug}.txt"
    if txt.exists():
        m = re.search(r"[?&]v=([\w-]{11})", txt.read_text(encoding="utf-8", errors="replace"))
        if m:
            info["video_id"] = m.group(1)
    info["titulo"] = info.get("titulo") or slug
    return info


def _biblioteca_um(slug: str, destino: str):
    _um_thread()
    import io
    import contextlib
    import shutil
    sys.path.insert(0, str(AQUI))
    pasta = Path(destino) / slug
    if (pasta / "AMT-APC - Dificil - previa.mp3").exists():
        return slug, True, 0.0
    (pasta / "cache").mkdir(parents=True, exist_ok=True)
    for f in ("transcricao.json", "amtapc_medio.mid"):
        shutil.copy(LOTE / "saida" / slug / "cache" / f, pasta / "cache" / f)
    info = _info_musica(slug)
    meta = {k: v for k, v in info.items() if v}
    (pasta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    import gerar
    _renderizar = gerar.renderizar_previas_pendentes
    gerar.renderizar_previas_pendentes = lambda *a, **k: _renderizar(2)   # vários processos ao mesmo tempo
    sys.argv = ["gerar.py", str(LOTE / "audio" / f"{slug}.wav"), "--leve", "--nivel", "todos", "--saida", destino,
                "--pasta", slug, "--titulo", info["titulo"], "--subtitulo", info.get("artista") or "Transcrição automática",
                "--reusar-cache"]
    t0, buf = time.time(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            gerar.main()
        ok = True
    except BaseException:
        buf.write(traceback.format_exc())
        ok = False
    (LOTE / "logs").mkdir(exist_ok=True)
    (LOTE / "logs" / f"biblioteca_{slug}.log").write_text(buf.getvalue(), encoding="utf-8")
    return slug, ok, time.time() - t0


def biblioteca(a):
    destino = LOTE / "biblioteca"
    destino.mkdir(parents=True, exist_ok=True)
    slugs = sorted(p.parent.parent.name for p in (LOTE / "saida").glob("*/cache/transcricao.json")
                   if (LOTE / "audio" / f"{p.parent.parent.name}.wav").exists())
    if a.musicas:
        slugs = [s_ for s_ in slugs if s_ in set(a.musicas.split(","))]
    if a.limite:
        slugs = slugs[:a.limite]
    t0, erros = time.time(), []
    with ProcessPoolExecutor(a.trabalhadores) as ex:
        fut = [ex.submit(_biblioteca_um, s_, str(destino)) for s_ in slugs]
        for i, f in enumerate(as_completed(fut), 1):
            slug, ok, dt = f.result()
            if not ok:
                erros.append(slug)
            print(f"[{i}/{len(fut)}] {'ok  ' if ok else 'ERRO'} {slug} {dt:.0f} s (total {(time.time() - t0) / 60:.1f} min)",
                  flush=True)
    print(f"{len(slugs) - len(erros)} ok, {len(erros)} com erro: {erros[:20]}")


# ------------------------------------------------------------------ medir

def _medir_um(pasta: str, com_dedos: bool):
    _um_thread()
    sys.path.insert(0, str(AQUI))
    import regressao
    import qualidade
    pasta = Path(pasta)
    r = {}
    for nivel in NIVEIS:
        xml = pasta / "editaveis" / f"AMT-APC - {nivel}.musicxml"
        if not xml.exists():
            continue
        try:
            if not com_dedos:
                regressao.dedos_sobrepostos = lambda x: 0
            m = regressao.medir_partitura(xml, nivel)
            m.update(qualidade.medir_xml(xml, nivel.lower(), pasta))
            m["acid_por_100"] = round(100 * m["acidentes"] / m["notas"], 2)
            m["sup_por_100"] = round(100 * m["suplementares"] / m["notas"], 2)
            m["dificeis_por_min"] = round(m["dificeis"] / max(m["duracao_s"] / 60, .5), 3)
            r[nivel] = m
        except Exception as e:
            r[nivel] = {"erro": f"{type(e).__name__}: {e}"}
    return pasta.name, r


def medir(a):
    saida = LOTE / (a.saida or "saida")
    pastas = sorted(p for p in saida.iterdir() if (p / "editaveis").is_dir())
    if a.limite:
        pastas = pastas[:a.limite]
    res, t0 = {}, time.time()
    with ProcessPoolExecutor(a.trabalhadores) as ex:
        fut = [ex.submit(_medir_um, str(p), a.dedos) for p in pastas]
        for i, f in enumerate(as_completed(fut), 1):
            nome, r = f.result()
            res[nome] = r
            if i % 20 == 0 or i == len(fut):
                print(f"[{i}/{len(fut)}] {(time.time() - t0) / 60:.1f} min", flush=True)
    destino = LOTE / f"medidas_{a.nome}.json"
    destino.write_text(json.dumps(res, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"salvo em {destino}")


# ------------------------------------------------------------------ resumo

def _agregados(res):
    import numpy as np
    out = {}
    for nivel in NIVEIS:
        chaves = {}
        for musica, r in res.items():
            m = r.get(nivel) or {}
            if "erro" in m:
                continue
            for k, v in m.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    chaves.setdefault(k, []).append(float(v))
        out[nivel] = {k: dict(media=float(np.mean(v)), p50=float(np.median(v)), p90=float(np.percentile(v, 90)),
                              zero=float(np.mean(np.array(v) == 0)), n=len(v)) for k, v in sorted(chaves.items())}
    return out


def resumo(a):
    res = json.loads((LOTE / f"medidas_{a.nome}.json").read_text(encoding="utf-8"))
    ag = _agregados(res)
    contra = None
    if a.contra:
        outro = json.loads((LOTE / f"medidas_{a.contra}.json").read_text(encoding="utf-8"))
        comuns = set(res) & set(outro)
        ag = _agregados({k: res[k] for k in comuns})
        contra = _agregados({k: outro[k] for k in comuns})
        print(f"{len(comuns)} músicas em comum")
    erros = sum("erro" in (r.get(n) or {}) for r in res.values() for n in NIVEIS)
    print(f"{len(res)} músicas, {erros} partituras com erro de medida")
    for nivel in NIVEIS:
        print(f"\n== {nivel}")
        for k, s in ag[nivel].items():
            linha = f"  {k:28s} média {s['media']:8.2f}  p50 {s['p50']:8.2f}  p90 {s['p90']:8.2f}  zero {s['zero']:4.0%}"
            if contra and k in contra[nivel]:
                c = contra[nivel][k]
                linha += f"   | antes {c['media']:8.2f} ({s['media'] - c['media']:+.2f})"
            print(linha)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("etapa", choices=("lista", "baixar", "preparar", "amtapc", "gerar", "biblioteca", "medir", "resumo"))
    ap.add_argument("--fonte", default="")
    ap.add_argument("--limite", type=int, default=0)
    ap.add_argument("--musicas", default="")
    ap.add_argument("--trabalhadores", type=int, default=12)
    ap.add_argument("--reusar-cache", action="store_true")
    ap.add_argument("--lista", default="", help="gerar: só as músicas de trabalho/lote/<arquivo> (.json de medidas ou .txt)")
    ap.add_argument("--pular-prontos", action="store_true", help="gerar: pula músicas com as 3 partituras prontas")
    ap.add_argument("--extra", default="", help="opções a mais pro gerar.py (ex.: '--sem-ajuste')")
    ap.add_argument("--ajustes", default="", help='JSON: {"tocavel.desfazer_sincopes.min_dur": 1.0, "maos.PERFIL": {...}}')
    ap.add_argument("--saida", default="", help="subpasta de trabalho/lote (padrão: saida)")
    ap.add_argument("--nome", default="base")
    ap.add_argument("--contra", default="")
    ap.add_argument("--dedos", action="store_true", help="medir também dedos sobrepostos (renderiza no Verovio)")
    a = ap.parse_args()
    {"lista": lista, "baixar": baixar, "preparar": preparar, "amtapc": amtapc, "gerar": gerar_lote, "biblioteca": biblioteca, "medir": medir, "resumo": resumo}[a.etapa](a)


if __name__ == "__main__":
    main()
