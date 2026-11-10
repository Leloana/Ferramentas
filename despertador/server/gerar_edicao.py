"""Monta uma edição: narração (ElevenLabs) + música local, manifesto e publicação atômica.

Uso:
  .venv\\Scripts\\python.exe gerar_edicao.py conteudo\\2026-11-10\\roteiro.json ^
      --musica ..\\..\\karaoke\\server\\songs\\so-nice-summer-samba-marcos-valle

`--musica` aceita um arquivo de áudio ou uma pasta do karaokê (vocal.mp3 + backing_track.mp3,
que são misturados num arquivo novo; os originais não são tocados).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import config
import voz

SCHEMA = 1


def duracao(arquivo: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arquivo)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return round(float(out), 2)


def sha256(arquivo: Path) -> str:
    h = hashlib.sha256()
    with arquivo.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def preparar_musica(origem: Path, destino: Path) -> None:
    if origem.is_dir():
        vocal, base = origem / "vocal.mp3", origem / "backing_track.mp3"
        if not (vocal.exists() and base.exists()):
            sys.exit(f"Pasta {origem} sem vocal.mp3 e backing_track.mp3")
        filtro = "[0:a][1:a]amix=inputs=2:normalize=0,afade=t=in:d=2,alimiter=limit=0.9,loudnorm=I=-16:TP=-1.5"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(vocal), "-i", str(base), "-filter_complex", filtro]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(origem), "-af", "afade=t=in:d=2,loudnorm=I=-16:TP=-1.5"]
    subprocess.run(cmd + ["-ar", "44100", "-ac", "2", "-b:a", "192k", str(destino)], check=True)


def normalizar_narracao(bruto: Path, destino: Path) -> None:
    # Pequeno silêncio no início e volume parecido com o da música.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(bruto),
                    "-af", "adelay=600:all=1,loudnorm=I=-15:TP=-1.5", "-ar", "44100", "-b:a", "128k", str(destino)],
                   check=True)


def proximo_id(data: str) -> str:
    n = 1
    while (config.EDICOES / f"{data}-r{n}").exists():
        n += 1
    return f"{data}-r{n}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("roteiro", type=Path)
    ap.add_argument("--musica", type=Path)
    args = ap.parse_args()

    roteiro = json.loads(args.roteiro.read_text(encoding="utf-8"))
    data = roteiro["editorial_date"]
    texto = roteiro["texto"].strip()
    if not roteiro.get("fontes"):
        sys.exit("Roteiro sem fontes: não publico notícia sem atribuição.")

    edicao_id = proximo_id(data)
    tmp = config.EDICOES / f".tmp-{edicao_id}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        bruto = tmp / "narracao_bruta.mp3"
        chamou = voz.sintetizar(texto, bruto, motivo=f"edição {edicao_id}")
        print(f"Narração: {'ElevenLabs' if chamou else 'cache'} ({len(texto)} caracteres; "
              f"gasto acumulado {voz.gasto_total()}/{config.TETO_TOTAL_CREDITOS} créditos)")
        normalizar_narracao(bruto, tmp / "narracao.mp3")
        bruto.unlink()

        arquivos = [("narracao", "narration", tmp / "narracao.mp3")]
        if args.musica:
            preparar_musica(args.musica, tmp / "musica.mp3")
            arquivos.append(("musica", "music", tmp / "musica.mp3"))

        agora = datetime.now(ZoneInfo(config.FUSO)).replace(microsecond=0)
        assets = []
        for nome, papel, arq in arquivos:
            d = duracao(arq)
            if d < 3:
                raise RuntimeError(f"{arq.name} curto demais ({d}s)")
            assets.append({
                "id": f"{edicao_id}-{nome}", "role": papel,
                "path": f"/v1/assets/{edicao_id}-{nome}", "file": arq.name,
                "mime_type": "audio/mpeg", "bytes": arq.stat().st_size,
                "sha256": sha256(arq), "duration_seconds": d,
            })
        manifesto = {
            "schema_version": SCHEMA, "edition_id": edicao_id, "editorial_date": data,
            "timezone": config.FUSO, "generated_at": agora.isoformat(),
            "expires_at": (agora + timedelta(hours=config.VALIDADE_HORAS)).isoformat(),
            "title": roteiro.get("titulo", ""), "script": texto,
            "sources": roteiro["fontes"], "music": roteiro.get("musica"), "assets": assets,
        }
        (tmp / "manifest.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")

        final = config.EDICOES / edicao_id
        tmp.rename(final)
        ponteiro = config.ATUAL.with_suffix(".tmp")
        ponteiro.write_text(edicao_id, encoding="utf-8")
        ponteiro.replace(config.ATUAL)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    total = sum(a["duration_seconds"] for a in assets)
    print(f"Edição publicada: {edicao_id} ({total:.0f}s de áudio) em {final}")


if __name__ == "__main__":
    main()
