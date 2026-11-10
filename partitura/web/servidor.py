"""Interface web da Partitura: busca no YouTube, prévia, geração em fila e biblioteca.

Rodar:  cd partitura; .\\venv\\Scripts\\python.exe run.py     (http://127.0.0.1:8030)
"""
from __future__ import annotations

import asyncio
import json
import shutil
import queue
import re
import subprocess
import sys
import threading
import time
import unicodedata
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

RAIZ = Path(__file__).resolve().parent.parent  # partitura/
SAIDA = RAIZ / "saida"
ENTRADA = RAIZ / "entrada"
PREVIAS = RAIZ / "web" / "cache_previas"
ESTATICO = RAIZ / "web" / "static"
PYTHON = sys.executable

NIVEIS = ("facil", "medio", "dificil")
NIVEL_ARQ = {"facil": "Facil", "medio": "Medio", "dificil": "Dificil"}
VERSOES = ("Acordes", "Hibrido", "Pop2Piano", "AMT-APC", "HibridoAMT")
TIPOS_PREVIA = {".m4a": "audio/mp4", ".mp4": "audio/mp4", ".webm": "audio/webm", ".mp3": "audio/mpeg"}
ID_RE = re.compile(r"^[\w-]{11}$")

app = FastAPI(title="Partitura")


@app.middleware("http")
async def sem_cache_na_pagina(request, call_next):
    """index/app.js/style.css sempre revalidados: senão o navegador roda o JS velho depois de uma atualização."""
    resp = await call_next(request)
    caminho = request.url.path
    if not caminho.startswith(("/api/", "/arquivos/")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# ----------------------------------------------------------------------------- YouTube

def _limpa_titulo(t: str) -> str:
    t = re.sub(r"[\(\[][^\)\]]*(official|oficial|video|vídeo|clipe|audio|áudio|lyric|letra|visualizer|hd|4k|remaster)[^\)\]]*[\)\]]",
               "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" -|")


def separar_artista_titulo(titulo: str, canal: str) -> tuple[str, str]:
    t = _limpa_titulo(titulo)
    canal = re.sub(r"\s*-\s*Topic$", "", canal or "").strip()
    for sep in (" - ", " – ", " — ", " | "):
        if sep in t:
            a, b = t.split(sep, 1)
            b = re.split(r"\s[|–—-]\s", b)[0]  # "Artista | Música | Inédito" -> "Música"
            return a.strip(), _limpa_titulo(b)
    return canal, t


@app.get("/api/busca")
async def busca(q: str, limite: int = 8):
    q = (q or "").strip()
    if len(q) < 2:
        raise HTTPException(400, "Digite o nome da música ou do artista.")
    import yt_dlp

    def _buscar():
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(f"ytsearch{max(1, min(limite, 12))}:{q}", download=False)

    try:
        info = await asyncio.to_thread(_buscar)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Não foi possível buscar no YouTube agora ({e}).")
    saida = []
    for e in (info or {}).get("entries") or []:
        vid = e.get("id")
        if not vid or not ID_RE.match(vid):
            continue
        canal = e.get("channel") or e.get("uploader") or ""
        artista, titulo = separar_artista_titulo(e.get("title") or "", canal)
        saida.append({
            "id": vid, "titulo_video": e.get("title") or "", "canal": canal,
            "artista": artista, "titulo": titulo, "duracao": e.get("duration"),
            "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
        })
    return {"resultados": saida}


_travas_previa: dict[str, asyncio.Lock] = {}


def _previa_em_cache(vid: str) -> Path | None:
    for p in PREVIAS.glob(f"{vid}.*"):
        if p.suffix in TIPOS_PREVIA and p.stat().st_size > 1000:
            return p
    return None


@app.get("/api/previa/{vid}")
async def previa(vid: str):
    """Áudio do vídeo pra ouvir antes de gerar (baixa uma vez e guarda)."""
    if not ID_RE.match(vid):
        raise HTTPException(400, "Vídeo inválido.")
    import yt_dlp
    trava = _travas_previa.setdefault(vid, asyncio.Lock())
    async with trava:
        achado = _previa_em_cache(vid)
        if not achado:
            PREVIAS.mkdir(parents=True, exist_ok=True)
            opts = {"format": "bestaudio[ext=m4a]/bestaudio", "outtmpl": str(PREVIAS / f"{vid}.%(ext)s"),
                    "quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True}

            def _baixar():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={vid}"])
            try:
                await asyncio.to_thread(_baixar)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(502, f"Não foi possível tocar a prévia ({e}).")
            achado = _previa_em_cache(vid)
            # guarda só as 30 mais recentes
            arquivos = sorted(PREVIAS.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            for velho in arquivos[30:]:
                velho.unlink(missing_ok=True)
        if not achado:
            raise HTTPException(502, "Não foi possível tocar a prévia.")
    return FileResponse(achado, media_type=TIPOS_PREVIA[achado.suffix])


# ----------------------------------------------------------------------------- fila de geração

class Pedido(BaseModel):
    video_id: str
    titulo: str
    artista: str = ""
    niveis: list[str] = ["medio"]
    versoes: list[str] = ["Acordes", "Hibrido"]
    idioma: str = "auto"
    estilo: int = Field(default=1, ge=1, le=21)
    introducao: str = ""          # "", calma, lenta, emotiva, animada, epica
    final: str = ""               # idem, final gerado
    acompanhamento: str = ""      # idem, esquerda da música inteira (versão Acordes)
    variacao: int = Field(default=0, ge=0, le=99)
    escrita_ja: str = "romaji"    # romaji ou kana (letra em japonês)
    separador: str = "htdemucs"   # htdemucs ou htdemucs_6s (experimento)


JOBS: dict[str, dict] = {}
FILA: "queue.Queue[str]" = queue.Queue()


def nome_pasta(titulo: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", titulo).strip() or "sem_titulo"


def _slug(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:60] or "musica"


def _pasta_livre(titulo: str, artista: str, vid: str) -> str:
    """Pasta da música; se já existe outra gravação com o mesmo título, acrescenta o artista."""
    nome = nome_pasta(titulo)
    for cand in (nome, nome_pasta(f"{titulo} ({artista})") if artista else None, f"{nome} [{vid}]"):
        if not cand:
            continue
        meta = SAIDA / cand / "meta.json"
        if not (SAIDA / cand).exists():
            return cand
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("video_id") == vid:
                return cand
        except (OSError, ValueError):
            pass
    return f"{nome} [{vid}]"


def _progresso(job: dict, linha: str):
    total = max(1, len(job["niveis"]) * len(job["versoes"]))
    marcos = [("[demucs]", 12, "Separando voz e instrumentos"), ("[batidas]", 20, "Detectando o pulso"),
              ("[melodia] extraindo", 25, "Lendo a melodia cantada"), ("[acordes]", 35, "Detectando os acordes"),
              ("[letra] transcrevendo", 40, "Ouvindo a letra (Whisper)"),
              ("[letra] letra oficial:", 0, "Letra oficial encontrada (LRCLIB)"),
              ("[pop2piano] carregando", 0, "Gerando arranjo com IA (Pop2Piano)"),
              ("[amt-apc] gerando", 0, "Gerando arranjo com IA (AMT-APC)")]
    for marca, pct, etapa in marcos:
        if linha.startswith(marca):
            if pct:
                job["progresso"] = max(job["progresso"], pct)
            job["etapa"] = etapa
    if linha.startswith("=== nível"):
        job["etapa"] = "Escrevendo partitura — " + linha.strip("= ").split("(")[0].replace("nível ", "nível ")
    if linha.startswith("[ok]"):
        job["feitos"] += 1
        job["progresso"] = max(job["progresso"], 50 + int(50 * job["feitos"] / total) - 1)


def _rodar(job: dict):
    vid = job["video_id"]
    ENTRADA.mkdir(exist_ok=True)
    wav = ENTRADA / f"{_slug(job['titulo'])}_{vid}.wav"
    if not wav.exists():
        job["etapa"], job["progresso"] = "Baixando do YouTube", 3
        import yt_dlp
        opts = {"format": "bestaudio/best", "outtmpl": str(wav.with_suffix(".%(ext)s")), "quiet": True,
                "no_warnings": True, "noplaylist": True,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}]}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={vid}"])
    job["progresso"] = 8
    cmd = [PYTHON, str(RAIZ / "gerar.py"), str(wav), "--titulo", job["titulo"],
           "--subtitulo", job["artista"] or "Transcrição automática", "--pasta", job["pasta"],
           "--nivel", ",".join(job["niveis"]), "--idioma", job["idioma"],
           "--estilo", str(job.get("estilo", 1))]
    if job["artista"]:
        cmd += ["--artista", job["artista"]]
    if job.get("introducao"):
        cmd += ["--introducao", job["introducao"]]
    if job.get("final"):
        cmd += ["--final", job["final"]]
    if job.get("acompanhamento"):
        cmd += ["--acompanhamento", job["acompanhamento"]]
    if job.get("introducao") or job.get("final"):
        cmd += ["--variacao", str(job.get("variacao", 0))]
    if job.get("escrita_ja") == "kana":
        cmd += ["--escrita-ja", "kana"]
    if job.get("separador") == "htdemucs_6s":
        cmd += ["--separador", "htdemucs_6s"]
    if job.get("reusar_cache"):
        cmd.append("--reusar-cache")
    if "Hibrido" in job["versoes"]:
        cmd.append("--hibrido")
    if "Pop2Piano" in job["versoes"]:
        cmd.append("--pop2piano")
    if "AMT-APC" in job["versoes"]:
        cmd.append("--amtapc")
    proc = subprocess.Popen(cmd, cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", env={**__import__("os").environ,
                                                                     "PYTHONIOENCODING": "utf-8"})
    for linha in proc.stdout:
        linha = linha.rstrip()
        if not linha or "Warning" in linha or "%|" in linha:
            continue
        job["log"].append(linha)
        job["log"] = job["log"][-60:]
        _progresso(job, linha)
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("a geração falhou: " + " | ".join(job["log"][-4:]))
    meta_p = SAIDA / job["pasta"] / "meta.json"
    meta = {}
    if meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta.update({"video_id": vid, "titulo": job["titulo"], "artista": job["artista"],
                 "estilo_pop2piano": job.get("estilo", 1),
                 "introducao": job.get("introducao") or None, "final": job.get("final") or None,
                 "acompanhamento": job.get("acompanhamento") or None,
                 "idioma": job.get("idioma", "auto"), "escrita_ja": job.get("escrita_ja", "romaji"),
                 "separador": job.get("separador", "htdemucs"),
                 "variacao_introducao": job.get("variacao", 0),
                 "atualizado": time.strftime("%Y-%m-%d %H:%M")})
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _trabalhador():
    while True:
        jid = FILA.get()
        job = JOBS.get(jid)
        if not job or job["status"] != "fila":   # cancelado ou removido enquanto esperava
            continue
        job["status"], job["inicio"] = "rodando", time.time()
        try:
            _rodar(job)
            job["status"], job["progresso"], job["etapa"] = "pronto", 100, "Pronto"
        except Exception as e:  # noqa: BLE001
            job["status"], job["etapa"] = "erro", str(e)[:500]
        finally:
            job["fim"] = time.time()


threading.Thread(target=_trabalhador, daemon=True).start()


@app.post("/api/gerar")
async def gerar(p: Pedido):
    if not ID_RE.match(p.video_id):
        raise HTTPException(400, "Vídeo inválido.")
    niveis = [n for n in NIVEIS if n in p.niveis] or ["medio"]
    versoes = [v for v in VERSOES if v in p.versoes] or ["Acordes"]
    titulo = (p.titulo or "").strip() or "Sem título"
    teores = ("calma", "lenta", "emotiva", "animada", "epica")
    if any(x and x not in teores for x in (p.introducao, p.final, p.acompanhamento)):
        raise HTTPException(400, "Teor de introdução ou final inválido.")
    if p.escrita_ja not in ("romaji", "kana") or p.separador not in ("htdemucs", "htdemucs_6s"):
        raise HTTPException(400, "Opção de escrita ou separador inválida.")
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "video_id": p.video_id, "titulo": titulo, "artista": p.artista.strip(),
                 "pasta": _pasta_livre(titulo, p.artista.strip(), p.video_id), "niveis": niveis,
                 "versoes": versoes, "idioma": p.idioma or "auto", "estilo": p.estilo,
                 "introducao": p.introducao, "final": p.final, "acompanhamento": p.acompanhamento,
                 "variacao": p.variacao, "escrita_ja": p.escrita_ja, "separador": p.separador,
                 "status": "fila", "etapa": "Na fila",
                 "progresso": 0, "feitos": 0, "log": [], "criado": time.time()}
    FILA.put(jid)
    return JOBS[jid]


class PedidoVariacao(BaseModel):
    pasta: str


@app.post("/api/variacao")
async def variacao(p: PedidoVariacao):
    """Outra variação da introdução/final gerados: guarda a atual em variacoes/vN e gera a
    próxima a partir do cache (sem separar nem transcrever de novo)."""
    pasta = (SAIDA / p.pasta).resolve()
    if not pasta.is_relative_to(SAIDA.resolve()) or not (pasta / "meta.json").exists():
        raise HTTPException(404, "Música não encontrada.")
    meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
    if not (meta.get("introducao") or meta.get("final")) or not meta.get("video_id"):
        raise HTTPException(400, "Esta música não tem introdução nem final gerados.")
    atual = int(meta.get("variacao_introducao") or 0)
    guardar = pasta / "variacoes" / f"v{atual}"
    guardar.mkdir(parents=True, exist_ok=True)
    niveis, versoes = set(), set()
    for f in pasta.iterdir():
        m = ARQ_RE.match(f.name)
        if m:
            shutil.copy2(f, guardar / f.name)
            niveis.add(m.group(2).lower())
            versoes.add(m.group(1))
    if (pasta / "editaveis").exists():
        shutil.copytree(pasta / "editaveis", guardar / "editaveis", dirs_exist_ok=True)
    flags = set()
    if versoes & {"Hibrido", "HibridoAMT"}:
        flags.add("Hibrido")
    if versoes & {"AMT-APC", "HibridoAMT"}:
        flags.add("AMT-APC")
    if "Pop2Piano" in versoes:
        flags.add("Pop2Piano")
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "video_id": meta["video_id"], "titulo": meta.get("titulo") or p.pasta,
                 "artista": meta.get("artista", ""), "pasta": p.pasta,
                 "niveis": [n for n in NIVEIS if n in niveis] or ["medio"],
                 "versoes": ["Acordes"] + sorted(flags), "idioma": meta.get("idioma", "auto"),
                 "escrita_ja": meta.get("escrita_ja", "romaji"), "separador": meta.get("separador", "htdemucs"),
                 "estilo": meta.get("estilo_pop2piano", 1), "introducao": meta.get("introducao") or "",
                 "final": meta.get("final") or "", "acompanhamento": meta.get("acompanhamento") or "",
                 "variacao": atual + 1, "reusar_cache": True,
                 "status": "fila", "etapa": "Na fila", "progresso": 0, "feitos": 0, "log": [],
                 "criado": time.time()}
    FILA.put(jid)
    return JOBS[jid]


@app.get("/api/jobs")
async def jobs():
    return {"jobs": sorted(JOBS.values(), key=lambda j: j["criado"], reverse=True)}


@app.delete("/api/jobs/{jid}")
async def tirar_job(jid: str):
    """Cancela um pedido que ainda está na fila ou tira da lista um que já terminou."""
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "Pedido não encontrado.")
    if job["status"] == "rodando":
        raise HTTPException(409, "Este pedido já está rodando.")
    del JOBS[jid]
    return {"ok": True}


@app.get("/api/jobs/{jid}")
async def job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "Pedido não encontrado.")
    return JOBS[jid]


# ----------------------------------------------------------------------------- biblioteca

ARQ_RE = re.compile(r"^(Acordes|HibridoAMT|Hibrido|Pop2Piano|AMT-APC) - (Facil|Medio|Dificil)(?: - previa)?\.(pdf|mp3)$")


@app.get('/api/partitura')
async def partitura(arquivo: str, layout: str = "pagina"):
    xml=(SAIDA/arquivo).resolve()
    if not xml.is_relative_to(SAIDA.resolve()) or xml.suffix.lower()!='.musicxml':
        raise HTTPException(400,'Partitura inválida.')
    if not xml.is_file():
        raise HTTPException(404,'Partitura não encontrada.')
    from web.partitura import renderizar
    try:
        return await asyncio.to_thread(renderizar,xml,layout)
    except (ValueError,OSError) as e:
        __import__('logging').getLogger('uvicorn.error').exception('Falha ao desenhar %s',xml.name)
        raise HTTPException(422,str(e))


@app.get("/api/musicas")
async def musicas():
    lista = []
    if not SAIDA.exists():
        return {"musicas": lista}
    for pasta in SAIDA.iterdir():
        if not pasta.is_dir():
            continue
        meta = {}
        try:
            meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        arquivos: dict = {}
        for f in pasta.iterdir():
            m = ARQ_RE.match(f.name)
            if not m:
                continue
            versao, nivel, ext = m.groups()
            item = arquivos.setdefault(nivel.lower(), {}).setdefault(versao, {})
            item["previa" if ext == "mp3" else "pdf"] = f"{pasta.name}/{f.name}"
        if not arquivos:
            continue
        lista.append({
            "pasta": pasta.name, "titulo": meta.get("titulo") or pasta.name, "artista": meta.get("artista", ""),
            "video_id": meta.get("video_id"), "arquivos": arquivos,
            "introducao": meta.get("introducao"), "final": meta.get("final"),
            "acompanhamento": meta.get("acompanhamento"), "atualizado": meta.get("atualizado"),
            "variacao": meta.get("variacao_introducao", 0),
            "variacoes": sorted(d.name for d in (pasta / "variacoes").iterdir() if d.is_dir())
            if (pasta / "variacoes").exists() else [],
            "original": f"{pasta.name}/Original.mp3" if (pasta / "Original.mp3").exists() else None,
            "editaveis": sorted(f"{pasta.name}/editaveis/{f.name}" for f in (pasta / "editaveis").glob("*.musicxml"))
            if (pasta / "editaveis").exists() else [],
            "mtime": max(f.stat().st_mtime for f in pasta.iterdir()),
        })
    lista.sort(key=lambda m: m["mtime"], reverse=True)
    return {"musicas": lista}


SAIDA.mkdir(exist_ok=True)
app.mount("/arquivos", StaticFiles(directory=SAIDA), name="arquivos")
app.mount("/", StaticFiles(directory=ESTATICO, html=True), name="estatico")
