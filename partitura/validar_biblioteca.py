"""Valida a biblioteca inteira antes/depois de uma mudança, num comando só (rodar na Windows).

    .\\venv\\Scripts\\python.exe validar_biblioteca.py              # tudo: antes, regenerar, depois, relatório, página
    .\\venv\\Scripts\\python.exe validar_biblioteca.py --rapido     # regenera do cache (só escrita da partitura)
    .\\venv\\Scripts\\python.exe validar_biblioteca.py --etapas relatorio,pagina --dir trabalho\\validacao_...
    .\\venv\\Scripts\\python.exe validar_biblioteca.py -- --introducao calma --final calma   (repassa ao gerar.py)

Etapas (pasta `trabalho/validacao_<data>/`):
1. antes      cópia da biblioteca (`antes/`) + métricas (`antes.json`)
2. regenerar  `gerar.py` de cada música com os mesmos níveis/versões (áudio do cache/transcricao.json)
3. depois     métricas da biblioteca nova (`depois.json`)
4. relatorio  `relatorio.md`: média por versão/nível antes × depois e se a dificuldade cresce
              de fácil pra difícil (descritores do RubricNet)
5. pagina     `pagina/index.html`: comparação às cegas, um trecho de 4 compassos por música e nível
Métricas: metricas.py (METRICAS_VALIDACAO.md). Sem LLM.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
ARQ_RE = re.compile(r"^(Acordes|HibridoAMT|Hibrido|Pop2Piano|AMT-APC) - (Facil|Medio|Dificil)\.pdf$")
ETAPAS = ("antes", "regenerar", "depois", "relatorio", "pagina")


def versoes_da_pasta(pasta: Path):
    return sorted(f"{m.group(1)} - {m.group(2)}" for f in pasta.iterdir() if (m := ARQ_RE.match(f.name)))


def medir_biblioteca(biblioteca: Path, destino: Path, com_audio=True):
    import metricas
    tudo = {}
    for pasta in sorted(p for p in biblioteca.iterdir() if p.is_dir()):
        for vn in versoes_da_pasta(pasta):
            t0 = time.time()
            try:
                tudo[f"{pasta.name}/{vn}"] = metricas.medir_versao(pasta, vn, com_audio=com_audio)
            except Exception as e:   # uma partitura quebrada não derruba a validação
                tudo[f"{pasta.name}/{vn}"] = dict(erro=str(e)[:200])
            print(f"[metricas] {pasta.name} / {vn} ({time.time() - t0:.1f} s)", flush=True)
    destino.write_text(json.dumps(tudo, ensure_ascii=False, indent=1), encoding="utf-8")
    return tudo


def copiar_biblioteca(biblioteca: Path, destino: Path):
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(biblioteca, destino, ignore=shutil.ignore_patterns("variacoes", "visor_*.json"))


def _slug(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def achar_audio(pasta: Path, meta: dict) -> Path | None:
    """Áudio de entrada de uma música sem cache/transcricao.json (biblioteca anterior ao cache):
    pelo video_id no nome do arquivo em entrada/, senão pelo título."""
    entrada = AQUI / "entrada"
    arqs = sorted(entrada.glob("*.wav")) + sorted(entrada.glob("*.mp3"))
    vid = meta.get("video_id")
    if vid:
        achados = [a for a in arqs if vid in a.stem]
        if achados:
            return achados[0]
    slug = _slug(meta.get("titulo") or pasta.name)
    achados = [a for a in arqs if a.stem.startswith(slug)]
    if len(achados) > 1:   # ex.: chega_de_saudade_..._instrumental × _montreal: desempata pelo artista
        art = set(_slug(meta.get("artista", "")).split("_"))
        achados.sort(key=lambda a: -len(art & set(a.stem.split("_"))))
    return achados[0] if achados else None


def regenerar(biblioteca: Path, rapido: bool, extra: list[str], so: set[str] | None = None):
    erros = []
    for pasta in sorted(p for p in biblioteca.iterdir() if p.is_dir()):
        if so and pasta.name not in so:
            continue
        vs = versoes_da_pasta(pasta)
        if not vs:
            print(f"[regenerar] {pasta.name}: sem partituras, pulando")
            continue
        meta = json.loads((pasta / "meta.json").read_text(encoding="utf-8")) if (pasta / "meta.json").exists() else {}
        transc = pasta / "cache" / "transcricao.json"
        t = json.loads(transc.read_text(encoding="utf-8")) if transc.exists() else {}
        audio = Path(t["audio"]) if t.get("audio") else achar_audio(pasta, meta)
        if rapido and not transc.exists():
            erros.append(f"{pasta.name}: --rapido precisa de cache/transcricao.json")
            continue
        if audio is None or not audio.exists():
            erros.append(f"{pasta.name}: áudio de entrada não encontrado ({audio})")
            continue
        niveis = sorted({v.split(" - ")[1].lower() for v in vs})
        nomes = {v.split(" - ")[0] for v in vs}
        cmd = [sys.executable, "-u", "-X", "utf8", str(AQUI / "gerar.py"), str(audio), "--pasta", pasta.name,
               "--saida", str(biblioteca), "--titulo", meta.get("titulo") or pasta.name,
               "--nivel", ",".join(niveis), "--idioma", t.get("idioma") or "auto"]
        if meta.get("artista"):
            cmd += ["--artista", meta["artista"], "--subtitulo", meta["artista"]]
        if nomes & {"Hibrido", "HibridoAMT"}:
            cmd.append("--hibrido")
        if nomes & {"AMT-APC", "HibridoAMT"}:
            cmd.append("--amtapc")
        if "Pop2Piano" in nomes:
            cmd += ["--pop2piano", "--estilo", str(meta.get("estilo_pop2piano", 1))]
        if rapido:
            cmd.append("--reusar-cache")
        cmd += extra
        print(f"[regenerar] {pasta.name}: {' '.join(cmd[4:])}", flush=True)
        t0 = time.time()
        r = subprocess.run(cmd, cwd=AQUI)
        if r.returncode:
            erros.append(f"{pasta.name}: gerar.py saiu com {r.returncode}")
        print(f"[regenerar] {pasta.name} em {time.time() - t0:.0f} s", flush=True)
    return erros


# ------------------------------------------------------------------ relatório

CAMPOS = [("fidelidade", "qmax", "maior é melhor"), ("fidelidade", "desvio_dtw_s", "menor é melhor"),
          ("melodia", "mca", "maior é melhor"), ("melodia", "f1", "maior é melhor"),
          ("grave_embolado", "por_minuto", "menor é melhor"), ("groove_esquerda", None, "estável"),
          ("direita", "notas_por_s", ""), ("esquerda", "notas_por_s", ""),
          ("esquerda", "deslocamento_por_s", ""), ("direita", "entropia", ""), ("esquerda", "lempel_ziv", ""),
          ("tensao", "tensile_strain.media", "tensão tonal (spiral array)"), ("tensao", "cloud_momentum.media", ""),
          ("qualidade_melodia", "fora_do_tom", "% menor é melhor"), ("qualidade_melodia", "repetidas", "% menor é melhor"),
          ("qualidade_melodia", "nao_no_topo", "% menor é melhor")]


def _valor(r, a, b):
    if not isinstance(r, dict):
        return None
    v = r.get(a)
    for parte in (b.split(".") if b is not None else []):
        v = v.get(parte) if isinstance(v, dict) else None
    return v if isinstance(v, (int, float)) else None


def relatorio(antes: dict, depois: dict, destino: Path):
    grupos = {}
    for chave in set(antes) | set(depois):
        vn = chave.split("/", 1)[1]
        grupos.setdefault(vn, []).append(chave)
    linhas = ["# Validação da biblioteca", "", f"{len(depois)} partituras depois, {len(antes)} antes.", ""]
    for vn in sorted(grupos):
        linhas += [f"## {vn}", "", "| métrica | antes | depois | |", "|---|---|---|---|"]
        for a, b, sentido in CAMPOS:
            va = [x for k in grupos[vn] if (x := _valor(antes.get(k), a, b)) is not None]
            vd = [x for k in grupos[vn] if (x := _valor(depois.get(k), a, b)) is not None]
            if not va and not vd:
                continue
            fa = f"{np.mean(va):.3f}" if va else "—"
            fd = f"{np.mean(vd):.3f}" if vd else "—"
            linhas.append(f"| {a}{'.' + b if b else ''} | {fa} | {fd} | {sentido} |")
        linhas.append("")
    # dificuldade crescendo fácil < médio < difícil, por música e versão
    linhas += ["## Dificuldade por nível (depois)", "",
               "Notas/s e deslocamento da mão devem crescer de fácil pra difícil.", ""]
    quebras = []
    for chave in depois:
        musica, vn = chave.split("/", 1)
        versao, nivel = vn.split(" - ")
        if nivel != "Facil":
            continue
        trio = [depois.get(f"{musica}/{versao} - {n}") for n in ("Facil", "Medio", "Dificil")]
        if any(t is None or "erro" in t for t in trio):
            continue
        for mao in ("direita", "esquerda"):
            v = [_valor(t, mao, "notas_por_s") for t in trio]
            if None not in v and not (v[0] <= v[1] <= v[2]):
                quebras.append(f"- {musica} · {versao} · {mao}: notas/s {v}")
    linhas += quebras or ["Sem quebras."]
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def main():
    argv = sys.argv[1:]
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    argv = argv[:argv.index("--")] if "--" in argv else argv
    ap = argparse.ArgumentParser()
    ap.add_argument("--biblioteca", type=Path, default=AQUI / "saida")
    ap.add_argument("--dir", type=Path, default=AQUI / "trabalho" / f"validacao_{time.strftime('%Y%m%d_%H%M')}")
    ap.add_argument("--etapas", default=",".join(ETAPAS))
    ap.add_argument("--rapido", action="store_true", help="regenera do cache (--reusar-cache)")
    ap.add_argument("--sem-audio", action="store_true", help="pula a fidelidade à gravação (mais rápido)")
    ap.add_argument("--so", default="", help="só estas músicas (pastas separadas por vírgula) na regeneração")
    a = ap.parse_args(argv)
    etapas = [e.strip() for e in a.etapas.split(",") if e.strip()]
    a.dir.mkdir(parents=True, exist_ok=True)
    if "antes" in etapas:
        print("== antes ==", flush=True)
        copiar_biblioteca(a.biblioteca, a.dir / "antes")
        medir_biblioteca(a.dir / "antes", a.dir / "antes.json", not a.sem_audio)
    if "regenerar" in etapas:
        print("== regenerar ==", flush=True)
        erros = regenerar(a.biblioteca, a.rapido, extra, set(a.so.split(",")) if a.so else None)
        (a.dir / "erros_regenerar.txt").write_text("\n".join(erros), encoding="utf-8")
        for e in erros:
            print("[erro]", e)
    if "depois" in etapas:
        print("== depois ==", flush=True)
        medir_biblioteca(a.biblioteca, a.dir / "depois.json", not a.sem_audio)
    if "relatorio" in etapas:
        antes = json.loads((a.dir / "antes.json").read_text(encoding="utf-8"))
        depois = json.loads((a.dir / "depois.json").read_text(encoding="utf-8"))
        print("[relatorio]", relatorio(antes, depois, a.dir / "relatorio.md"))
    if "pagina" in etapas:
        from comparacao_cega import montar_pagina
        print("[pagina]", montar_pagina(a.dir / "antes", a.biblioteca, a.dir / "pagina"))


if __name__ == "__main__":
    main()
