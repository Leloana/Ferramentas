"""Métricas pra validar as partituras geradas (ver METRICAS_VALIDACAO.md). Sem LLM.

Por partitura (MusicXML + prévia + cache da música):
- fidelidade(): Qmax (recorrência cruzada de croma, Serrà et al. 2009, via librosa) e desvio
  do caminho de DTW entre a prévia e a gravação original; introdução/final gerados cortados.
- melodia(): acerto de croma da melodia (MCA, mir_eval.melody) e F1 de notas
  (mir_eval.transcription) da direita contra a voz detectada (cache/transcricao.json).
- dificuldade(): descritores do RubricNet por mão (Ramoneda et al. 2024): entropia de
  alturas, extensão, altura média, deslocamento da mão por segundo, IOI médio, Lempel-Ziv.
- grave_embolado(): intervalos da esquerda abaixo do "low interval limit" por minuto.
- groove(): constância do padrão rítmico da esquerda entre compassos (1 − Hamming médio).
- tensao(): tensão do spiral array (pacote `partitura`, Herremans & Chew), se instalado.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

# menor nota (MIDI) em que cada intervalo ainda soa claro no piano ("low interval limits",
# regra de arranjo/orquestração); abaixo disso a esquerda embola
from maos import LIMITE_GRAVE  # noqa: E402  (mesma tabela da correção)


def notas_do_xml(xml: Path):
    """[{inicio, fim (s da partitura), pitch, mao 'direita'|'esquerda', letra}]"""
    from sincronia import notas_ligadas, preparar_musicxml
    _, segmentos = preparar_musicxml(Path(xml).read_text(encoding="utf-8"))
    saida = []
    for n in notas_ligadas(segmentos):
        pauta = n["voz"].split(":")[1] if ":" in n["voz"] else "1"
        saida.append(dict(inicio=float(n["inicio"]), fim=float(n["fim"]), pitch=int(n["pitch"]),
                          mao="direita" if pauta == "1" else "esquerda", letra=bool(n.get("letra"))))
    return saida


# ------------------------------------------------------------------ dificuldade

def _entropia(valores):
    if not len(valores):
        return 0.0
    _, c = np.unique(valores, return_counts=True)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum())


def _lempel_ziv(seq):
    """Complexidade de Lempel-Ziv (LZ76) normalizada pelo tamanho."""
    s = [str(x) for x in seq]
    n = len(s)
    if n < 2:
        return 0.0
    i, c, l, k, kmax = 0, 1, 1, 1, 1
    while True:
        if s[i + k - 1] == s[l + k - 1]:
            k += 1
            if l + k > n:
                c += 1
                break
        else:
            kmax = max(k, kmax)
            i += 1
            if i == l:
                c += 1
                l += kmax
                if l + 1 > n:
                    break
                i, k, kmax = 0, 1, 1
            else:
                k = 1
    return c * math.log2(n) / n


def dificuldade(notas, mao):
    ns = sorted((n for n in notas if n["mao"] == mao), key=lambda n: n["inicio"])
    if not ns:
        return {}
    ataques = {}
    for n in ns:
        ataques.setdefault(round(n["inicio"], 3), []).append(n["pitch"])
    tempos = sorted(ataques)
    conjuntos = [tuple(sorted(ataques[t])) for t in tempos]
    centros = [float(np.mean(c)) for c in conjuntos]
    dur = max(n["fim"] for n in ns) - ns[0]["inicio"]
    desloc = sum(abs(b - a) for a, b in zip(centros, centros[1:]))
    pitches = [n["pitch"] for n in ns]
    return dict(entropia=round(_entropia(pitches), 3), extensao=int(max(pitches) - min(pitches)),
                altura_media=round(float(np.mean(pitches)), 1),
                deslocamento_por_s=round(desloc / dur, 3) if dur > 0 else 0.0,
                ioi_medio=round(float(np.mean(np.diff(tempos))), 3) if len(tempos) > 1 else 0.0,
                lempel_ziv=round(_lempel_ziv(conjuntos), 3), notas_por_s=round(len(ns) / dur, 3) if dur > 0 else 0.0)


# ------------------------------------------------------------------ grave embolado e groove

def grave_embolado(notas):
    """Intervalos simultâneos da esquerda abaixo do limite, por minuto."""
    esq = [n for n in notas if n["mao"] == "esquerda"]
    if not esq:
        return dict(por_minuto=0.0, casos=0)
    ataques = {}
    for n in esq:
        ataques.setdefault(round(n["inicio"], 3), []).append(n["pitch"])
    casos = 0
    for ps in ataques.values():
        ps = sorted(set(ps))
        for a, b in zip(ps, ps[1:]):
            iv = b - a
            if iv in LIMITE_GRAVE and a < LIMITE_GRAVE[iv]:
                casos += 1
    minutos = (max(n["fim"] for n in esq) - min(n["inicio"] for n in esq)) / 60
    return dict(por_minuto=round(casos / minutos, 2) if minutos > 0 else 0.0, casos=casos)


def groove(notas, bpm, mao="esquerda", divisoes=16):
    """1 − distância de Hamming média entre padrões de ataque de compassos vizinhos (4/4)."""
    ns = [n for n in notas if n["mao"] == mao]
    if not ns or bpm <= 0:
        return None
    padroes = {}
    for n in ns:
        q = round(n["inicio"] * bpm / 60 * divisoes / 4) / divisoes * 4   # tempo na grade (sem erro de ponto flutuante)
        c = int(q // 4 + 1e-9)
        pos = int(round((q - 4 * c) / 4 * divisoes)) % divisoes
        padroes.setdefault(c, np.zeros(divisoes, dtype=bool))[pos] = True
    cs = sorted(padroes)
    dist = [np.mean(padroes[a] != padroes[b]) for a, b in zip(cs, cs[1:]) if b == a + 1]
    return round(1 - float(np.mean(dist)), 3) if dist else None


# ------------------------------------------------------------------ melodia contra a voz

def melodia(notas, transcricao, mapa):
    """MCA e F1 de notas da melodia (notas com letra da direita) contra a voz detectada.

    mapa: {bt, idx, desloc, bpm} (cache/sincronia_original.json da versão) pra levar o tempo
    da partitura pro tempo da gravação."""
    import mir_eval
    bt, idx = np.asarray(mapa["bt"]), np.asarray(mapa["idx"])
    para_original = lambda s: float(np.interp(s * mapa["bpm"] / 60 - mapa["desloc"], idx, bt))  # noqa: E731
    mel = [n for n in notas if n["mao"] == "direita" and n["letra"]]
    if not mel:
        return {}
    est_int = np.array([[para_original(n["inicio"]), para_original(n["fim"])] for n in mel])
    est_p = np.array([440 * 2 ** ((n["pitch"] - 69) / 12) for n in mel])
    ref = [n for n in transcricao.get("notas", [])]
    saida = {}
    if ref:
        ref_int = np.array([[a, max(b, a + .02)] for a, b, _ in ref])
        ref_p = np.array([440 * 2 ** ((p - 69) / 12) for *_, p in ref])
        p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
            ref_int, ref_p, est_int, est_p, onset_tolerance=.1, pitch_tolerance=50, offset_ratio=None)
        saida.update(precisao=round(p, 3), revocacao=round(r, 3), f1=round(f, 3))
    quadros = (transcricao.get("diagnostico") or {}).get("quadros")
    if quadros:
        t = np.arange(len(quadros["midi"])) * .01
        voz = (np.asarray(quadros["per"]) > .45) & (np.asarray(quadros["db"]) > -30)
        ref_f = np.where(voz, 440 * 2 ** ((np.asarray(quadros["midi"]) - 69) / 12), 0)
        est_f = np.zeros_like(t)
        for (a, b), f in zip(est_int, est_p):
            est_f[(t >= a) & (t < b)] = f
        rv, rc, ev, ec = mir_eval.melody.to_cent_voicing(t, ref_f, t, est_f)
        saida["mca"] = round(float(mir_eval.melody.raw_chroma_accuracy(rv, rc, ev, ec)), 3)
    return saida


# ------------------------------------------------------------------ fidelidade à gravação

def fidelidade(previa: Path, original: Path, corte_ini=0.0, corte_fim=0.0, sr=22050, hop=2048):
    """Qmax (maior trilha da recorrência cruzada, normalizada) e desvio do caminho de DTW.

    corte_ini/corte_fim: segundos da prévia que não existem na gravação (intro/final gerados)."""
    import librosa
    y1, _ = librosa.load(str(previa), sr=sr, mono=True)
    y2, _ = librosa.load(str(original), sr=sr, mono=True)
    y1 = y1[int(corte_ini * sr): len(y1) - int(corte_fim * sr) if corte_fim else None]
    c1 = librosa.feature.chroma_cqt(y=y1, sr=sr, hop_length=hop) + 1e-4   # silêncio não vira NaN
    c2 = librosa.feature.chroma_cqt(y=y2, sr=sr, hop_length=hop) + 1e-4
    if c1.shape[1] < 8 or c2.shape[1] < 8:
        return {}
    # recorrência cruzada com empilhamento de atrasos (Serrà); rqa acha a maior trilha diagonal
    e1 = librosa.feature.stack_memory(c1, n_steps=6, delay=1)
    e2 = librosa.feature.stack_memory(c2, n_steps=6, delay=1)
    xsim = librosa.segment.cross_similarity(e1, e2, metric="cosine", mode="affinity", k=None)
    score, caminho = librosa.sequence.rqa(xsim, knight_moves=True, backtrack=True)
    qmax = float(score.max()) / min(c1.shape[1], c2.shape[1])
    D, wp = librosa.sequence.dtw(X=c1, Y=c2, metric="cosine")
    wp = wp[::-1]
    coef = np.polyfit(wp[:, 0], wp[:, 1], 1)
    desvio = float(np.std(wp[:, 1] - np.polyval(coef, wp[:, 0]))) * hop / sr
    return dict(qmax=round(qmax, 4), desvio_dtw_s=round(desvio, 3),
                custo_dtw=round(float(D[-1, -1]) / len(wp), 4))


# ------------------------------------------------------------------ tensão (opcional)

def tensao(xml: Path):
    try:
        import partitura as pt
        from partitura.musicanalysis import estimate_tonaltension
    except Exception:
        return None
    try:
        tt = estimate_tonaltension(pt.load_musicxml(str(xml)))
    except Exception as e:  # partitura pode recusar algum detalhe do MusicXML
        return dict(erro=str(e)[:120])
    saida = {}
    for campo in ("cloud_diameter", "cloud_momentum", "tensile_strain"):
        v = np.asarray(tt[campo], dtype=float)
        saida[campo] = dict(media=round(float(np.mean(v)), 3), p90=round(float(np.percentile(v, 90)), 3))
    return saida


# ------------------------------------------------------------------ uma partitura

def medir_versao(pasta: Path, versao_nivel: str, com_audio=True):
    """Métricas de saida/<musica>/<Versao - Nivel>.  Devolve dict (campos ausentes se faltar dado)."""
    xml = pasta / "editaveis" / f"{versao_nivel}.musicxml"
    if not xml.exists():
        return None
    notas = notas_do_xml(xml)
    cache = pasta / "cache"
    transcricao = json.loads((cache / "transcricao.json").read_text(encoding="utf-8")) \
        if (cache / "transcricao.json").exists() else {}
    sinc = json.loads((cache / "sincronia_original.json").read_text(encoding="utf-8")) \
        if (cache / "sincronia_original.json").exists() else {}
    bpm = float(transcricao.get("bpm") or 120)
    nivel = versao_nivel.split(" - ")[-1].lower()
    corte_ini = corte_fim = 0.0
    for nome_, attr in (("introducao", "ini"), ("final", "fim")):
        arq = cache / f"{nome_}_{nivel}.json"
        if arq.exists():
            seg = 4 * json.loads(arq.read_text(encoding="utf-8"))["compassos"] * 60 / bpm
            if attr == "ini":
                corte_ini = seg
            else:
                corte_fim = seg
    # dificuldade/grave/groove só do corpo da música: introdução e final gerados à parte
    fim_total = max((n["fim"] for n in notas), default=0)
    corpo = [n for n in notas if corte_ini - 1e-6 <= n["inicio"] < fim_total - corte_fim - 1e-6]
    r = dict(direita=dificuldade(corpo, "direita"), esquerda=dificuldade(corpo, "esquerda"),
             grave_embolado=grave_embolado(corpo), groove_esquerda=groove(corpo, bpm))
    if sinc.get("versoes", {}).get(versao_nivel) is not None and transcricao:
        mapa = dict(bt=sinc["bt"], idx=sinc["idx"], desloc=sinc["versoes"][versao_nivel], bpm=bpm)
        try:
            r["melodia"] = melodia(notas, transcricao, mapa)
        except ImportError:
            r["melodia"] = None
    previa, original = pasta / f"{versao_nivel} - previa.mp3", pasta / "Original.mp3"
    if com_audio and previa.exists() and original.exists():
        r["fidelidade"] = fidelidade(previa, original, corte_ini, corte_fim)
    t = tensao(xml)
    if t is not None:
        r["tensao"] = t
    return r
