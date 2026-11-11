"""Dinâmica escrita pela gravação (sem LLM): p / mp / mf / f por trecho, a partir da intensidade da música.

Intensidade por compasso = média em dB dos quadros mais fortes (metade de cima, ignora pausas da
bateria). Os níveis são relativos à própria música (gravações pop são comprimidas: o refrão é poucos
dB mais forte que a estrofe, mas é ele que o pianista toca forte). Programação dinâmica escolhe um
nível por compasso: custo = distância da intensidade ao centro do nível + troca de nível (no mínimo
`MIN_COMPASSOS` compassos por trecho, como numa partitura de verdade: estrofe mp, refrão f).
Sai em `marcas` do gerar.py: (posição em tempos, "dinamica", "mf").
"""
from __future__ import annotations

import numpy as np

NIVEIS = ("p", "mp", "mf", "f")
CENTROS = (-1.4, -0.45, 0.35, 1.2)   # em desvios-padrão da intensidade da música
# faixas de quantis (da intensidade da própria música) que definem o centro de p | mp | mf | f;
# None = centros fixos em CENTROS
QUANTIS = (.15, .45, .8)
TROCA = 2.5                           # custo de mudar de nível
MIN_COMPASSOS = 4
DB_MINIMO = 3.0                       # música com menos variação que isso (dB, p10–p90) fica num nível só


def intensidade_por_compasso(audio, bt, idx, compasso=4, sr=22050):
    import librosa
    y, sr = librosa.load(str(audio), sr=sr, mono=True)
    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    db = 20 * np.log10(rms + 1e-6)
    t = librosa.frames_to_time(np.arange(len(db)), sr=sr, hop_length=hop)
    pos = np.interp(t, bt, idx)
    ini, fim = int(np.floor(idx[0] / compasso)), int(np.ceil(idx[-1] / compasso))
    out = []
    for k in range(max(ini, 0), fim):
        m = (pos >= k * compasso) & (pos < (k + 1) * compasso)
        if m.sum() < 4:
            out.append((k, None))
            continue
        v = np.sort(db[m])[len(db[m]) // 2:]
        out.append((k, float(v.mean())))
    return out


def niveis_por_compasso(intens):
    vals = np.array([v for _, v in intens if v is not None])
    if len(vals) < MIN_COMPASSOS or np.percentile(vals, 90) - np.percentile(vals, 10) < DB_MINIMO:
        return [(k, "mf") for k, v in intens if v is not None][:1]
    z = [(k, None if v is None else (v - np.median(vals)) / (vals.std() + 1e-6)) for k, v in intens]
    ks = [k for k, v in z if v is not None]
    vs = [v for k, v in z if v is not None]
    centros = CENTROS
    if QUANTIS:   # centro de cada nível = mediana da intensidade na faixa de quantis dele, nesta música
        zs = np.array(vs)
        cortes = np.quantile(zs, (0,) + tuple(QUANTIS) + (1,))
        centros = tuple(float(np.median(zs[(zs >= a) & (zs <= b)])) if ((zs >= a) & (zs <= b)).any() else c
                        for a, b, c in zip(cortes, cortes[1:], CENTROS))
    n, L = len(vs), len(NIVEIS)
    # estado: (nível, compassos desde a troca, limitado a MIN_COMPASSOS)
    INF = float("inf")
    custo = np.full((L, MIN_COMPASSOS + 1), INF)
    for a in range(L):
        custo[a, 1] = abs(vs[0] - centros[a])
    volta = []
    for i in range(1, n):
        novo = np.full((L, MIN_COMPASSOS + 1), INF)
        v = {}
        for a in range(L):
            d = abs(vs[i] - centros[a])
            for c in range(1, MIN_COMPASSOS + 1):   # fica no nível
                if custo[a, c] < INF:
                    c2 = min(c + 1, MIN_COMPASSOS)
                    if custo[a, c] + d < novo[a, c2]:
                        novo[a, c2] = custo[a, c] + d
                        v[(a, c2)] = (a, c)
            for b in range(L):                       # troca (só depois de MIN_COMPASSOS)
                if b != a and custo[b, MIN_COMPASSOS] + TROCA + d < novo[a, 1]:
                    novo[a, 1] = custo[b, MIN_COMPASSOS] + TROCA + d
                    v[(a, 1)] = (b, MIN_COMPASSOS)
        custo = novo
        volta.append(v)
    a, c = np.unravel_index(np.argmin(custo), custo.shape)
    seq = [int(a)]
    for v in reversed(volta):
        a, c = v[(a, c)]
        seq.append(int(a))
    seq.reverse()
    out, ant = [], None
    for k, a in zip(ks, seq):
        if a != ant:
            out.append((k, NIVEIS[a]))
        ant = a
    return out


def marcas_de_dinamica(audio, bt, idx, compasso=4, inicio=0.0):
    """[(posição em tempos, "dinamica", nível)] nas trocas, a partir de `inicio` (1ª nota)."""
    trocas = niveis_por_compasso(intensidade_por_compasso(audio, bt, idx, compasso))
    marcas = []
    for k, nv in trocas:
        o = max(float(k * compasso), inicio)
        if marcas and abs(marcas[-1][0] - o) < 1e-6:
            marcas[-1] = (o, "dinamica", nv)
        else:
            marcas.append((o, "dinamica", nv))
    return marcas
