"""Figurinhas: baixa um vídeo (TikTok, X, YouTube, ...) e transforma um trecho em
figurinha de WhatsApp (.webp 512x512, animada <= 500 KB ou estática <= 100 KB)."""

import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).parent
WORK = BASE / "work"
WORK.mkdir(exist_ok=True)

LIMITE_ANIMADA = 500 * 1024
LIMITE_ESTATICA = 100 * 1024
DURACAO_MAX_VIDEO = 30 * 60  # não baixa vídeos com mais de 30 min
VALIDADE_TRABALHO = 2 * 3600  # apaga downloads com mais de 2 h
FONTE = Path("C:/Windows/Fonts/impact.ttf")

app = FastAPI(title="Figurinhas")


def limpar_antigos():
    agora = time.time()
    for pasta in WORK.iterdir():
        if pasta.is_dir() and agora - pasta.stat().st_mtime > VALIDADE_TRABALHO:
            shutil.rmtree(pasta, ignore_errors=True)


def pasta_do(id_: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", id_):
        raise HTTPException(400, "id inválido")
    pasta = WORK / id_
    if not pasta.is_dir():
        raise HTTPException(404, "vídeo expirou, baixe de novo")
    return pasta


class PedidoBaixar(BaseModel):
    url: str


class PedidoFigurinha(BaseModel):
    id: str
    inicio: float = Field(0, ge=0)
    duracao: float = Field(5, gt=0, le=10)
    modo: str = Field("cortar", pattern="^(cortar|encaixar|area)$")
    # modo "area": quadrado escolhido na tela, em frações do vídeo
    # (x, y = canto superior esquerdo / largura, altura; lado = fração do menor lado)
    area_x: float = Field(0, ge=0, le=1)
    area_y: float = Field(0, ge=0, le=1)
    area_lado: float = Field(1, gt=0.05, le=1)
    estatica: bool = False
    texto: str = Field("", max_length=60)


@app.post("/api/baixar")
def baixar(p: PedidoBaixar):
    url = p.url.strip()
    if not re.match(r"^https?://", url):
        raise HTTPException(400, "cole um link começando com http(s)://")
    limpar_antigos()
    id_ = uuid.uuid4().hex
    pasta = WORK / id_
    pasta.mkdir()

    def filtro(info, *, incomplete):
        dur = info.get("duration")
        if dur and dur > DURACAO_MAX_VIDEO:
            return "vídeo longo demais (máx. 30 min)"

    opcoes = {
        # só vídeo, até 720p, de preferência H.264 para o navegador tocar a prévia
        "format": "bv*[height<=720][vcodec^=avc1]/bv*[height<=720]/b[height<=720]/bv*/b",
        "outtmpl": str(pasta / "video.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "match_filter": filtro,
    }
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        shutil.rmtree(pasta, ignore_errors=True)
        msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
        raise HTTPException(422, f"não consegui baixar: {msg}")

    arquivos = [f for f in pasta.glob("video.*") if f.suffix != ".part"]
    if not arquivos:
        shutil.rmtree(pasta, ignore_errors=True)
        raise HTTPException(422, "o link não tem vídeo (ou foi barrado pelo filtro)")
    return {
        "id": id_,
        "titulo": info.get("title") or "",
        "duracao": info.get("duration") or 0,
        "video": f"/work/{id_}/{arquivos[0].name}",
    }


def filtro_video(p: PedidoFigurinha, pasta: Path, fps: int | None) -> str:
    partes = [f"fps={fps}"] if fps else []
    if p.modo == "cortar":
        partes += ["scale=512:512:force_original_aspect_ratio=increase", "crop=512:512"]
    elif p.modo == "area":
        lado = f"min(iw,ih)*{p.area_lado:.4f}"
        partes += [
            f"crop=w='{lado}':h='{lado}'"
            f":x='min(iw*{p.area_x:.4f},iw-ow)':y='min(ih*{p.area_y:.4f},ih-oh)'",
            "scale=512:512",
        ]
    else:
        partes += [
            "scale=512:512:force_original_aspect_ratio=decrease",
            "format=rgba",
            "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
        ]
    if p.texto.strip():
        # texto vai por arquivo para não precisar escapar nada no filtro
        (pasta / "texto.txt").write_text(p.texto.strip(), encoding="utf-8")
        fonte = str(FONTE).replace("\\", "/").replace(":", "\\:")
        partes.append(
            f"drawtext=fontfile='{fonte}':textfile=texto.txt:fontsize=64:fontcolor=white"
            ":borderw=5:bordercolor=black:x=(w-text_w)/2:y=h-text_h-28"
        )
    return ",".join(partes)


def gerar(p: PedidoFigurinha, pasta: Path, video: Path, saida: Path, fps: int | None, q: int,
          duracao: float):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{p.inicio:.3f}", "-i", str(video)]
    if p.estatica:
        cmd += ["-frames:v", "1"]
    else:
        cmd += ["-t", f"{duracao:.3f}", "-loop", "0"]
    cmd += ["-an", "-vf", filtro_video(p, pasta, fps), "-c:v", "libwebp",
            "-lossless", "0", "-q:v", str(q), "-compression_level", "6", str(saida)]
    r = subprocess.run(cmd, cwd=pasta, capture_output=True, text=True)
    if r.returncode != 0 or not saida.exists():
        raise HTTPException(500, f"ffmpeg falhou: {r.stderr.strip()[-400:]}")


@app.post("/api/figurinha")
def figurinha(p: PedidoFigurinha):
    pasta = pasta_do(p.id)
    video = next((f for f in pasta.glob("video.*") if f.suffix != ".part"), None)
    if not video:
        raise HTTPException(404, "vídeo não encontrado")
    pasta.touch()  # renova a validade

    nome = f"figurinha_{uuid.uuid4().hex[:8]}.webp"
    saida = pasta / nome
    limite = LIMITE_ESTATICA if p.estatica else LIMITE_ANIMADA
    # o tamanho depende quase só de fps x duração: baixa a qualidade, depois o fps
    # (até 10), a qualidade de novo e, se ainda não couber, encurta o trecho
    fps, q, duracao = (None, 80, 0) if p.estatica else (15, 60, p.duracao)
    for _ in range(8):
        gerar(p, pasta, video, saida, fps, q, duracao)
        tamanho = saida.stat().st_size
        if tamanho <= limite:
            break
        fator = limite / tamanho * 0.92
        if q > 30:
            q = 30
        elif fps and fps > 10:
            fps = max(10, int(fps * fator))
        elif q > 15:
            q = 15
        elif not p.estatica and duracao > 1:
            duracao = max(1.0, round(duracao * fator, 1))
        else:
            q = max(5, q - 10)
    tamanho = saida.stat().st_size
    return {
        "url": f"/work/{p.id}/{nome}",
        "tamanho": tamanho,
        "cabe": tamanho <= limite,
        "limite": limite,
        "duracao": duracao,
        "estatica": p.estatica,
    }


@app.get("/")
def inicio():
    return FileResponse(BASE / "static" / "index.html")


app.mount("/work", StaticFiles(directory=WORK), name="work")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
