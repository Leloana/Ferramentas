"""Experimento: acordes com 4 faixas (htdemucs) × 6 faixas (htdemucs_6s). PROXIMA_ETAPA §12.

    python experimento_6faixas.py entrada\\musica1.wav entrada\\musica2.wav [--referencias pasta]

Para cada música: separa nos dois modelos (cache em trabalho/<modelo>/), detecta acordes com
o "resto" (4 faixas) e com guitarra + piano (6 faixas), e mede:
- concordância entre os dois (mesma fundamental; mesma fundamental e qualidade);
- trocas de acorde por minuto (troca demais costuma ser ruído);
- se houver referência (`<pasta>/<nome do áudio>.csv`, linhas "inicio_s,fim_s,acorde", ex.
  "12.5,14.0,Am7"), acerto de cada um por janela contra os trechos conferidos à mão;
- tempo de separação de cada modelo.
Gera `trabalho/experimento_6faixas/relatorio.md`, `resultado.json` e `index.html` (ouvir
as faixas de piano e guitarra e ver os acordes lado a lado, por compasso).
Sem LLM: Demucs (separação) + croma e Viterbi já usados no gerar.py.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import subprocess
import time
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
NOMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
SUFIXO = {"maj": "", "m": "m", "7": "7", "maj7": "7M", "m7": "m7", "m7b5": "m7(b5)", "dim7": "°",
          "6": "6", "m6": "m6"}
FAMILIA = {"maj": "M", "7": "M", "maj7": "M", "6": "M", "m": "m", "m7": "m", "m6": "m", "m7b5": "d", "dim7": "d"}


def nome(r, t):
    return "—" if r is None else NOMES[r % 12] + SUFIXO.get(t, t)


def ler_acorde(txt: str):
    """'Am7' -> (9, 'm7'); 'Bb7M' -> (10, 'maj7'); 'F#m7(b5)' -> (6, 'm7b5'). None se não entender."""
    m = re.match(r"^\s*([A-Ga-g])([#b]?)(.*)$", txt or "")
    if not m:
        return None
    r = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[m.group(1).upper()]
    r = (r + {"#": 1, "b": -1, "": 0}[m.group(2)]) % 12
    s = m.group(3).replace(" ", "").lower()
    tabela = [("m7(b5)", "m7b5"), ("m7b5", "m7b5"), ("ø", "m7b5"), ("°", "dim7"), ("dim", "dim7"),
              ("m6", "m6"), ("m7", "m7"), ("7m", "maj7"), ("maj7", "maj7"), ("m", "m"),
              ("7", "7"), ("6", "6"), ("", "maj")]
    for suf, t in tabela:
        if s.startswith(suf) if suf else True:
            return r, t
    return None


def comparar_sequencias(a, b):
    """a, b: [(pos, raiz, tipo, ...)] nas mesmas janelas. Concordância por janela com acorde."""
    ja = {j: (r, t) for j, r, t, *_ in a}
    jb = {j: (r, t) for j, r, t, *_ in b}
    comuns = [j for j in ja if j in jb and ja[j][0] is not None and jb[j][0] is not None]
    if not comuns:
        return dict(janelas=0, mesma_fundamental=None, mesmo_acorde=None, mesma_familia=None)
    raiz = np.mean([ja[j][0] == jb[j][0] for j in comuns])
    igual = np.mean([ja[j] == jb[j] for j in comuns])
    fam = np.mean([ja[j][0] == jb[j][0] and FAMILIA.get(ja[j][1]) == FAMILIA.get(jb[j][1]) for j in comuns])
    return dict(janelas=len(comuns), mesma_fundamental=round(float(raiz), 3),
                mesmo_acorde=round(float(igual), 3), mesma_familia=round(float(fam), 3))


def trocas_por_minuto(acs, segundos_por_tempo, janela=2):
    seq = [(r, t) for _, r, t, *_ in acs if r is not None]
    trocas = sum(1 for x, y in zip(seq, seq[1:]) if x != y)
    minutos = len(acs) * janela * segundos_por_tempo / 60
    return round(trocas / minutos, 2) if minutos > 0 else None


def contra_referencia(acs, referencia, tempo_de_posicao, janela=2):
    """referencia: [(inicio_s, fim_s, (raiz, tipo))]. Acerto nas janelas que caem num trecho conferido."""
    certos_r = certos_f = total = 0
    for j, r, t, *_ in acs:
        meio = tempo_de_posicao(j + janela / 2)
        ref = next((rt for a, b, rt in referencia if a <= meio < b), None)
        if ref is None or r is None:
            continue
        total += 1
        certos_r += r == ref[0]
        certos_f += r == ref[0] and FAMILIA.get(t) == FAMILIA.get(ref[1])
    if not total:
        return dict(janelas=0, fundamental=None, familia=None)
    return dict(janelas=total, fundamental=round(certos_r / total, 3), familia=round(certos_f / total, 3))


def ler_referencia(arq: Path):
    saida = []
    with arq.open(encoding="utf-8") as f:
        for linha in csv.reader(f):
            if len(linha) < 3 or linha[0].strip().startswith("#"):
                continue
            ac = ler_acorde(linha[2])
            if ac:
                saida.append((float(linha[0]), float(linha[1]), ac))
    return saida


def _mp3(wav: Path, destino: Path, segundos=90):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-t", str(segundos),
                    "-b:a", "128k", str(destino)], check=True)


def main():
    import gerar
    ap = argparse.ArgumentParser()
    ap.add_argument("audios", nargs="+", type=Path)
    ap.add_argument("--referencias", type=Path, default=None)
    ap.add_argument("--saida", type=Path, default=AQUI / "trabalho" / "experimento_6faixas")
    a = ap.parse_args()
    a.saida.mkdir(parents=True, exist_ok=True)
    sr, resultados = 22050, []
    for audio in a.audios:
        audio = audio.resolve()
        tempos = {}
        stems = {}
        for modelo in ("htdemucs", "htdemucs_6s"):
            t0 = time.time()
            stems[modelo] = gerar.separar(audio, AQUI / "trabalho", modelo)
            tempos[modelo] = round(time.time() - t0, 1)
        s4, s6 = stems["htdemucs"], stems["htdemucs_6s"]
        mix = gerar.carregar(audio, sr)
        baixo = gerar.carregar(s4 / "bass.wav", sr)
        resto = gerar.carregar(s4 / "other.wav", sr)
        bateria = gerar.carregar(s4 / "drums.wav", sr)
        bt, bpm = gerar.batidas(mix, sr, bateria + .5 * baixo + .3 * resto)
        grade = gerar.Grade(bt, gerar.fase_compasso(bt, baixo, sr))
        acs4 = gerar.acordes(resto + .3 * baixo, baixo, sr, grade)
        harm6, _ = gerar.harmonia_das_faixas(s6, sr)
        baixo6 = gerar.carregar(s6 / "bass.wav", sr)
        n = min(len(harm6), len(baixo6))
        acs6 = gerar.acordes(harm6[:n] + .3 * baixo6[:n], baixo6, sr, grade)
        spb = 60 / bpm
        r = dict(musica=audio.stem, bpm=round(float(bpm), 1), tempo_separacao_s=tempos,
                 concordancia=comparar_sequencias(acs4, acs6),
                 trocas_por_minuto={"4 faixas": trocas_por_minuto(acs4, spb), "6 faixas": trocas_por_minuto(acs6, spb)})
        if a.referencias and (a.referencias / f"{audio.stem}.csv").exists():
            ref = ler_referencia(a.referencias / f"{audio.stem}.csv")
            pos_para_s = lambda p: float(np.interp(p, grade.idx, grade.bt))  # noqa: E731
            r["referencia"] = {"4 faixas": contra_referencia(acs4, ref, pos_para_s),
                               "6 faixas": contra_referencia(acs6, ref, pos_para_s)}
        pasta = a.saida / audio.stem
        pasta.mkdir(exist_ok=True)
        for faixa, wav in (("piano", s6 / "piano.wav"), ("guitarra", s6 / "guitar.wav"),
                           ("resto_6", s6 / "other.wav"), ("resto_4", s4 / "other.wav")):
            if wav.exists():
                _mp3(wav, pasta / f"{faixa}.mp3")
        compassos = {}
        for (j, r4, t4, *_), (_, r6, t6, *_) in zip(acs4, acs6):
            compassos.setdefault(int(j // 4) + 1, []).append((nome(r4, t4), nome(r6, t6)))
        r["compassos"] = compassos
        resultados.append(r)
        print(audio.stem, json.dumps({k: v for k, v in r.items() if k != "compassos"}, ensure_ascii=False))
    (a.saida / "resultado.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# Experimento 6 faixas", ""]
    for r in resultados:
        md += [f"## {r['musica']} ({r['bpm']} bpm)", "",
               f"- separação: {r['tempo_separacao_s']}",
               f"- concordância 4×6: {r['concordancia']}",
               f"- trocas/min: {r['trocas_por_minuto']}"]
        if "referencia" in r:
            md.append(f"- contra a referência: {r['referencia']}")
        md.append("")
    (a.saida / "relatorio.md").write_text("\n".join(md), encoding="utf-8")
    partes = ["<!doctype html><meta charset='utf-8'><title>Experimento 6 faixas</title>",
              "<style>body{font:15px system-ui;margin:20px;max-width:1000px}td,th{border:1px solid #ccc;"
              "padding:3px 6px}table{border-collapse:collapse}.d{background:#fde2c8}</style>",
              "<h1>Experimento 6 faixas</h1><p>Ouça as faixas e compare os acordes por compasso "
              "(4 faixas / 6 faixas; laranja = diferem).</p>"]
    for r in resultados:
        partes.append(f"<h2>{html.escape(r['musica'])}</h2><p>{html.escape(json.dumps(r['concordancia']))}</p>")
        for faixa in ("piano", "guitarra", "resto_6", "resto_4"):
            if (a.saida / r["musica"] / f"{faixa}.mp3").exists():
                partes.append(f"<div>{faixa}: <audio controls preload='none' src='{html.escape(r['musica'])}/{faixa}.mp3'></audio></div>")
        partes.append("<table><tr><th>compasso</th><th>4 faixas</th><th>6 faixas</th></tr>")
        for c, pares in r["compassos"].items():
            a4 = " ".join(p[0] for p in pares)
            a6 = " ".join(p[1] for p in pares)
            partes.append(f"<tr class='{'d' if a4 != a6 else ''}'><td>{c}</td><td>{a4}</td><td>{a6}</td></tr>")
        partes.append("</table>")
    (a.saida / "index.html").write_text("".join(partes), encoding="utf-8")
    print("relatório em", a.saida)


if __name__ == "__main__":
    main()
