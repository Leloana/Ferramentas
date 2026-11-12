"""Música com vocal -> partitura de piano (PDF + MusicXML + MIDI).

Pipeline "melodia + acordes":
  1. Demucs separa voz / baixo / bateria / resto.
  2. Mão direita: melodia do vocal (torchcrepe) quantizada nas batidas.
  3. Mão esquerda: acordes detectados (chroma do resto + baixo), em bloco a cada 2 tempos.
  4. Cifra em cima da pauta, MusicXML -> SVG (Verovio) -> PDF (Chrome headless).

Uso:
  python gerar.py entrada/musica.wav [--saida saida/] [--titulo "..."] [--pop2piano]
"""
from __future__ import annotations

import argparse
import json
import os
import time
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
SR_GRADE = 2  # subdivisões por tempo (definido pelo nível: 1 semínima, 2 colcheia, 4 semicolcheia)
GRADE_NIVEL = {"facil": 1, "medio": 2, "dificil": 4}

NOMES_PC = ["C", "C#", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B"]
NOMES_PC_BEMOL = ["C", "D-", "D", "E-", "E", "F", "G-", "G", "A-", "A", "B-", "B"]

# tipo de acorde -> (intervalos, kind do MusicXML/music21, sufixo da cifra)
TIPOS = {
    "maj": ([0, 4, 7], "major", ""),
    "m": ([0, 3, 7], "minor", "m"),
    "7": ([0, 4, 7, 10], "dominant-seventh", "7"),
    "maj7": ([0, 4, 7, 11], "major-seventh", "7M"),
    "m7": ([0, 3, 7, 10], "minor-seventh", "m7"),
    "m7b5": ([0, 3, 6, 10], "half-diminished-seventh", "m7(b5)"),
    "dim7": ([0, 3, 6, 9], "diminished-seventh", "°"),
    "6": ([0, 4, 7, 9], "major-sixth", "6"),
    "m6": ([0, 3, 7, 9], "minor-sixth", "m6"),
}


# ----------------------------------------------------------------------------- áudio

def carregar(path: Path, sr: int) -> np.ndarray:
    import librosa
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    return y


def separar(audio: Path, trabalho: Path, modelo: str = "htdemucs") -> Path:
    """Faixas do Demucs. htdemucs: voz/bateria/baixo/resto; htdemucs_6s também guitarra e
    piano (o piano vaza bastante, segundo o próprio Demucs; ver PROXIMA_ETAPA §12)."""
    destino = trabalho / modelo / audio.stem
    if (destino / "vocals.wav").exists():
        print(f"[demucs] já separado: {destino}")
        return destino
    print(f"[demucs] separando faixas ({modelo})...")
    subprocess.run([sys.executable, "-m", "demucs", "-n", modelo, "-d", "cuda",
                    "-o", str(trabalho), str(audio)], check=True)
    return destino


def harmonia_das_faixas(stems: Path, sr: int):
    """Sinal usado pra detectar acordes: guitarra + piano (+ resto mais fraco) quando a
    separação tem 6 faixas; senão o "resto" de sempre. Devolve (sinal, descrição)."""
    resto = carregar(stems / "other.wav", sr)
    if (stems / "guitar.wav").exists() and (stems / "piano.wav").exists():
        guitarra = carregar(stems / "guitar.wav", sr)
        piano = carregar(stems / "piano.wav", sr)
        n = min(len(resto), len(guitarra), len(piano))
        return guitarra[:n] + piano[:n] + .5 * resto[:n], "guitarra + piano + 0,5 x resto"
    return resto, "resto"


# ----------------------------------------------------------------------------- batidas

def batidas(mix: np.ndarray, sr: int, perc: np.ndarray) -> tuple[np.ndarray, float]:
    """Batidas em segundos, estendidas para trás até t<=0 e para frente até o fim."""
    import librosa
    env = librosa.onset.onset_strength(y=perc, sr=sr)
    tempo, frames = librosa.beat.beat_track(onset_envelope=env, sr=sr, start_bpm=120, tightness=120)
    bt = librosa.frames_to_time(frames, sr=sr)
    periodo = float(np.median(np.diff(bt)))
    dur = len(mix) / sr
    antes = []
    t = bt[0] - periodo
    while t > -periodo:
        antes.append(t)
        t -= periodo
    depois = []
    t = bt[-1] + periodo
    while t < dur + periodo:
        depois.append(t)
        t += periodo
    bt = np.concatenate([antes[::-1], bt, depois])
    return bt, 60.0 / periodo


def batidas_madmom(audio: Path, dur: float):
    """Batidas e tempo 1 pelo madmom (RNN + rede bayesiana dinâmica; Böck, Krebs e Widmer, ISMIR 2016),
    estendidas pra trás até t <= 0 e pra frente até o fim como em `batidas`. Devolve
    (bt, bpm, fase, batidas_por_compasso) ou None sem madmom.

    Medido 2026-11-11 nas 5 músicas de teste contra librosa + fase pela heurística: mais ataques do
    arranjo caindo no tempo (Águas 38 → 55%, Anna Júlia 51 → 63%), o grave no tempo 1 (Ode 16 → 38%,
    a heurística errava a fase em 2 tempos; Cálice 26 → 45%) e as repetições em número inteiro de
    compassos (Fuyu: a grade do librosa ganhava 13 batidas e a repetição caía em 38,5 compassos)."""
    try:
        from madmom.features.downbeats import DBNDownBeatTrackingProcessor, RNNDownBeatProcessor
    except Exception:
        return None
    r = DBNDownBeatTrackingProcessor(beats_per_bar=[3, 4], fps=100)(RNNDownBeatProcessor()(str(audio)))
    if len(r) < 8 or not (r[:, 1] == 1).any():
        return None
    bt, pos = r[:, 0].astype(float), r[:, 1].astype(int)
    por_compasso = int(pos.max())
    periodo = float(np.median(np.diff(bt)))
    primeiro_1 = int(np.where(pos == 1)[0][0])
    antes, t = [], bt[0] - periodo
    while t > -periodo:
        antes.append(t)
        t -= periodo
    depois, t = [], bt[-1] + periodo
    while t < dur + periodo:
        depois.append(t)
        t += periodo
    fase = (primeiro_1 + len(antes)) % por_compasso
    return np.concatenate([antes[::-1], bt, depois]), 60.0 / periodo, fase, por_compasso


def fase_compasso(bt: np.ndarray, baixo: np.ndarray, sr: int) -> int:
    """Escolhe qual batida (0..3) é o tempo 1: onde o baixo bate mais forte."""
    import librosa
    env = librosa.onset.onset_strength(y=baixo, sr=sr)
    t_env = librosa.times_like(env, sr=sr)
    forca = np.interp(bt, t_env, env)
    somas = [forca[f::4].mean() + 0.5 * forca[(f + 2) % 4::4].mean() for f in range(4)]
    return int(np.argmax(somas))


def fase_pelo_midi(bt: np.ndarray, mid: Path, grave: int = 55) -> int:
    """Modo leve: o tempo 1 pelas notas graves do arranjo do AMT-APC (força dos ataques nas batidas)."""
    import pretty_midi
    notas = [n for i in pretty_midi.PrettyMIDI(str(mid)).instruments for n in i.notes if n.pitch < grave]
    if not notas or len(bt) < 8:
        return 0
    forca = np.zeros(len(bt))
    for n in notas:
        k = int(np.argmin(np.abs(bt - n.start)))
        if abs(bt[k] - n.start) < .08:
            forca[k] += n.velocity * (1 + (60 - n.pitch) / 24)   # mais grave pesa mais
    somas = [forca[f::4].mean() + 0.5 * forca[(f + 2) % 4::4].mean() for f in range(4)]
    return int(np.argmax(somas))


def corrigir_fase(fase: int, acs, razao: float = 1.3):
    """O baixo bate forte no 1 e no 3: a fase pode sair meio compasso deslocada. A harmonia muda
    mais no tempo 1; se as trocas de acorde caem claramente mais no 3, anda 2 batidas.
    Devolve (fase, acs com as posições ajustadas, mudou)."""
    trocas, ant = {0: 0, 2: 0}, None
    for j, r, t, *_ in acs:
        if r is None:
            ant = None
            continue
        if ant is not None and (r, t) != ant and int(round(j)) % 4 in trocas:
            trocas[int(round(j)) % 4] += 1
        ant = (r, t)
    if trocas[2] <= max(4, razao * trocas[0]):
        return fase, acs, False
    nova = (fase + 2) % 4
    delta = fase - nova                      # posição = batida - fase
    return nova, [(j + delta, *resto) for j, *resto in acs], True


class Grade:
    """Converte tempo (s) <-> posição em tempos musicais, seguindo as batidas reais."""

    def __init__(self, bt: np.ndarray, fase: int):
        self.bt = bt
        self.idx = np.arange(len(bt), dtype=float) - fase  # batida `fase` vira posição 0

    @property
    def passo(self) -> float:
        """Menor duração da grade atual (o nível muda SR_GRADE deste módulo)."""
        return 1 / SR_GRADE

    def pos(self, t: float) -> float:
        return float(np.interp(t, self.bt, self.idx))

    def q(self, t: float) -> float:
        return round(self.pos(t) * SR_GRADE) / SR_GRADE


# ----------------------------------------------------------------------------- melodia

def melodia(voz: np.ndarray, sr: int, onsets_voz: np.ndarray, diagnostico=None) -> list[tuple[float, float, int]]:
    """Notas (inicio_s, fim_s, midi) da voz isolada."""
    import torch
    import torchcrepe
    from scipy.signal import medfilt

    hop = sr // 100  # 10 ms
    x = torch.tensor(voz, dtype=torch.float32)[None]
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    f0, per = torchcrepe.predict(x, sr, hop, fmin=65, fmax=1000, model="full",
                                 decoder=torchcrepe.decode.viterbi, return_periodicity=True,
                                 batch_size=1024, device=dev)
    f0 = f0[0].cpu().numpy()
    per = medfilt(per[0].cpu().numpy(), 5)

    # volume da voz por frame, pra ignorar vazamento de instrumento quando ninguém canta
    n = len(f0)
    # CREPE inclui um frame final quando a duração é múltipla do hop.
    # Sem padding, esse frame usa mean([]), produz NaN e invalida o
    # percentil de volume, descartando TODAS as notas da música.
    amostras = np.pad(voz[:n * hop], (0, max(0, n * hop - len(voz))))
    rms = np.sqrt(np.mean(amostras.reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    vozeado = (per > 0.45) & (db > np.percentile(db, 95) - 30)

    midi = 12 * np.log2(np.maximum(f0, 1) / 440.0) + 69
    midi = medfilt(midi, 5)

    notas: list[list] = []  # [ini_frame, fim_frame, [midis]]
    atual = None
    cand_cnt = 0
    for i in range(n):
        if not vozeado[i]:
            if atual:
                notas.append(atual)
            atual, cand_cnt = None, 0
            continue
        m = midi[i]
        if atual is None:
            atual = [i, i + 1, [m]]
            continue
        p = round(float(np.median(atual[2][-15:])))
        if abs(m - p) > 0.7:  # histerese: só troca de nota se ficar >= 40 ms em outra altura
            cand_cnt += 1
            if cand_cnt >= 4:
                ini = i - cand_cnt + 1
                atual[1] = ini
                atual[2] = atual[2][:len(atual[2]) - cand_cnt + 1]
                notas.append(atual)
                atual = [ini, i + 1, list(midi[ini:i + 1])]
                cand_cnt = 0
                continue
        else:
            cand_cnt = 0
        atual[1] = i + 1
        atual[2].append(m)
    if atual:
        notas.append(atual)

    # divide notas repetidas onde a voz tem ataque (sílaba nova na mesma altura)
    saida = []
    qualidades = []
    if diagnostico is not None:
        from protecao_melodia import qualidade_segmento
    for ini, fim, ms in notas:
        if not ms:
            continue
        cortes = [ini]
        for o in onsets_voz:
            fo = int(round(o * 100))
            if ini + 8 < fo < fim - 8:
                cortes.append(fo)
        cortes.append(fim)
        for a, b in zip(cortes[:-1], cortes[1:]):
            if b - a >= 6:  # >= 60 ms
                seg = midi[a:b]
                saida.append((a / 100, b / 100, int(round(float(np.median(seg))))))
                if diagnostico is not None:
                    qualidades.append(qualidade_segmento(midi,per,a,b))
    if diagnostico is not None:
        diagnostico['notas']=qualidades
        from palavras_sem_nota import quadros_do_detector
        diagnostico['quadros']=quadros_do_detector(midi,per,db)  # pra dar nota a palavra sem nota
    return saida


def quantizar_melodia(notas, grade: Grade) -> list[tuple]:
    """-> (ini_tempo, fim_tempo, midi, ini_s, fim_s); os segundos servem pra encaixar a letra."""
    q = []
    for ini, fim, p in notas:
        a, b = grade.q(ini), grade.q(fim)
        if b <= a:
            b = a + 1 / SR_GRADE
        q.append([a, b, p, ini, fim])
    q.sort()
    limpo = []
    for n in q:
        if limpo and n[0] == limpo[-1][0]:  # mesmo início: fica a mais longa
            if n[1] - n[0] > limpo[-1][1] - limpo[-1][0]:
                limpo[-1] = n
            continue
        limpo.append(n)
    for a, b in zip(limpo[:-1], limpo[1:]):
        if a[1] > b[0]:
            a[1] = b[0]
        elif b[0] - a[1] <= 1 / SR_GRADE:  # buraco minúsculo: legato
            a[1] = b[0]
    return [tuple(n) for n in limpo if n[1] > n[0]]


# ----------------------------------------------------------------------------- acordes

def _templates():
    nomes, mats = [], []
    for r in range(12):
        for tipo, (ints, _, _) in TIPOS.items():
            v = np.zeros(12)
            for i in ints:
                v[(r + i) % 12] = 1
            v[r] += 0.5  # tônica pesa um pouco mais
            nomes.append((r, tipo))
            mats.append(v / np.linalg.norm(v))
    return nomes, np.array(mats)


def croma_do_midi(mid: Path, grade: Grade, janelas, beats_por_janela=2, grave=55):
    """Croma por janela a partir das notas do arranjo (AMT-APC): duração dentro da janela × força,
    e a classe do baixo (nota grave mais longa). Devolve (cromas (n, 12), baixos [pc ou -1])."""
    import pretty_midi
    notas = [n for i in pretty_midi.PrettyMIDI(str(mid)).instruments for n in i.notes]
    ini = janelas[0] if janelas else 0
    c = np.zeros((len(janelas), 12))
    cb = np.zeros((len(janelas), 12))
    for n in notas:
        a, b = grade.pos(n.start), grade.pos(n.end)
        k = int((a - ini) // beats_por_janela)
        while 0 <= k < len(janelas) and ini + k * beats_por_janela < b:
            j = ini + k * beats_por_janela
            dur = min(b, j + beats_por_janela) - max(a, j)
            if dur > 0:
                w = dur * (n.velocity / 64.0)
                c[k, n.pitch % 12] += w
                if n.pitch < grave:
                    cb[k, n.pitch % 12] += w * (1 + (grave - n.pitch) / 12)
            k += 1
    baixos = [int(np.argmax(x)) if x.sum() > 0 else -1 for x in cb]
    return c, baixos


def acordes(harm: np.ndarray, baixo: np.ndarray, sr: int, grade: Grade, beats_por_janela=2,
            midi_arranjo: Path | None = None, fonte: str = "mistura"):
    """Lista (pos_tempo, root_pc, tipo, baixo_pc) a cada `beats_por_janela` tempos.

    fonte: "mistura" (croma do áudio), "ia" (croma das notas do arranjo do AMT-APC, `midi_arranjo`)
    ou "ambos" (média das semelhanças com os moldes)."""
    import librosa
    hop = 512
    ch = librosa.feature.chroma_cqt(y=harm, sr=sr, hop_length=hop)
    chb = librosa.feature.chroma_cqt(y=baixo, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("E1"), n_octaves=3)
    n = min(ch.shape[1], chb.shape[1])   # CQTs com faixas diferentes podem sair com 1 quadro de diferença
    ch, chb = ch[:, :n], chb[:, :n]
    t = librosa.times_like(ch, sr=sr, hop_length=hop)
    pos = np.array([grade.pos(x) for x in t])

    nomes, T = _templates()
    ini, fim = int(np.floor(pos.min())), int(np.ceil(pos.max()))
    janelas = list(range(ini - ini % beats_por_janela, fim, beats_por_janela))
    obs, bassp, energia = [], [], []
    for j in janelas:
        m = (pos >= j) & (pos < j + beats_por_janela)
        if m.sum() == 0:
            obs.append(np.zeros(len(nomes))); bassp.append(-1); energia.append(0); continue
        c = np.median(ch[:, m], axis=1)
        b = chb[:, m].mean(axis=1)
        energia.append(float(c.sum()))
        c = c / (np.linalg.norm(c) + 1e-9)
        s = T @ c
        bp = int(np.argmax(b))
        bassp.append(bp)
        s = s + 0.08 * np.array([1.0 if r == bp else 0.0 for r, _ in nomes])
        obs.append(s)
    obs = np.array(obs)
    if fonte != "mistura" and midi_arranjo is not None:
        ci, bi = croma_do_midi(midi_arranjo, grade, janelas, beats_por_janela)
        oi = []
        for c, bp in zip(ci, bi):
            if c.sum() <= 0:
                oi.append(np.zeros(len(nomes)))
                continue
            si = T @ (c / np.linalg.norm(c))
            oi.append(si + 0.08 * np.array([1.0 if r == bp else 0.0 for r, _ in nomes]))
        oi = np.array(oi)
        obs = oi if fonte == "ia" else (obs + oi) / 2

    # Viterbi: troca de acorde custa um pouco (evita pisca-pisca)
    K = len(nomes)
    troca = 0.12
    dp = obs[0].copy()
    back = np.zeros((len(obs), K), dtype=int)
    for i in range(1, len(obs)):
        melhor = dp.max()
        arg = int(dp.argmax())
        fica = dp
        muda = melhor - troca
        back[i] = np.where(fica >= muda, np.arange(K), arg)
        dp = np.maximum(fica, muda) + obs[i]
    k = int(dp.argmax())
    seq = [k]
    for i in range(len(obs) - 1, 0, -1):
        k = back[i, k]
        seq.append(k)
    seq = seq[::-1]

    limiar = 0.15 * np.percentile(energia, 90)
    out = []
    for j, k, bp, e in zip(janelas, seq, bassp, energia):
        if e < limiar:
            out.append((j, None, None, None))
        else:
            r, tipo = nomes[k]
            out.append((j, r, tipo, bp))
    return out


# ----------------------------------------------------------------------------- partitura

NOMES_PC_SUST = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _custo_armaduras(eventos) -> np.ndarray:
    from armaduras import custo_por_armadura
    return custo_por_armadura(eventos)


def armaduras_por_trecho(eventos_off, fim: float, frases=()) -> list[tuple[float, int]]:
    """Mudanças de armadura [(offset, sustenidos)]: ver armaduras.py."""
    from armaduras import armaduras_por_trecho as por_trecho
    return por_trecho(eventos_off, fim, frases)


def escolher_armadura(eventos) -> int:
    return int(np.argmin(_custo_armaduras(eventos))) - 6


# cifra (nome do acorde) em cima da pauta: o usuário pediu sem (2026-11-11, "atrapalha").
# O acorde detectado continua decidindo a grafia das notas; `--cifras` volta a desenhar.
MOSTRAR_CIFRAS = False


def acorde_com_grafia(r: int, kind: str, sustenidos: int):
    """ChordSymbol com a raiz na grafia (C#/D-, G#/A-...) que dá menos acidentes contra a armadura,
    sem dobrado bemol/sustenido (G#dim7 num tom com bemóis, não A-dim7 com G--)."""
    from music21 import harmony, key as m21key
    na_armadura = {p.step: p.alter for p in m21key.KeySignature(sustenidos).alteredPitches}
    padrao = (["C", "D-", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B"] if sustenidos < 0
              else (NOMES_PC_SUST if sustenidos >= 3 else NOMES_PC))[r]
    candidatos = [padrao] + [n for n in (NOMES_PC_SUST[r], NOMES_PC_BEMOL[r], NOMES_PC[r]) if n != padrao]
    melhor, menor = None, None
    for nome in dict.fromkeys(candidatos):
        cs = harmony.ChordSymbol(root=nome, kind=kind)
        custo = sum(abs(q.alter - na_armadura.get(q.step, 0)) + (10 if abs(q.alter) >= 2 else 0)
                    for q in cs.pitches)
        if menor is None or custo < menor:
            melhor, menor = cs, custo
    return melhor


# nota da escala da armadura sempre com a grafia da armadura (a cifra só decide as cromáticas).
# Antes, um acorde mal detectado (Sol♯maj7 em Sol♯ menor pede Fá𝄪 e vira Lá♭–Dó–Mi♭–Sol) levava
# até as notas da escala pra grafia enarmônica: Mi♭ e Lá♭ num tom de 5♯. Medido 2026-11-11 em 64
# músicas (lote.py): acidentes evitáveis 1,6 → 0 por 100 notas, acidentes −12 a −19%, notas iguais.
GRAFIA_ESCALA = True


def grafia_da_escala(sustenidos: int) -> dict[int, str]:
    """{classe de altura: nome} das 7 notas da escala maior da armadura (Mi♯ em Fá♯ maior, Dó♭ em Sol♭)."""
    ordem = "FCGDAEB" if sustenidos >= 0 else "BEADGCF"
    alt = {s_: (1 if sustenidos > 0 else -1) for s_ in ordem[:abs(sustenidos)]}
    base = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)
    return {(base[s_] + alt.get(s_, 0)) % 12: s_ + {1: "#", -1: "-"}.get(alt.get(s_, 0), "") for s_ in "CDEFGAB"}


def nomes_para(sustenidos: int) -> list[str]:
    if sustenidos < 0:
        return NOMES_PC_BEMOL
    return NOMES_PC_SUST if sustenidos >= 3 else NOMES_PC


def com_introducao(md, me, cf, intro, k=0):
    """Põe a introdução gerada nos compassos antes da música. intro = gerar_introducao(...);
    k = transposição já aplicada à música. Devolve (md, me, cifras, marcas)."""
    from introducao import NOME_TEOR
    i_md, i_me, i_cf, info = intro
    inicio = 4.0 * np.floor(min(e[0] for e in list(md) + list(me)) / 4)   # 1º compasso da música
    L = 4.0 * info["compassos"]
    md = [(o + inicio - L, d, [p + k for p in ps], *r) for o, d, ps, *r in i_md] + list(md)
    me = [(o + inicio - L, d, [p + k for p in ps]) for o, d, ps in i_me] + list(me)
    cf = [(o + inicio - L, (r + k) % 12, t) for o, r, t in i_cf] + [c for c in cf if c[0] >= inicio - 1e-6]
    marcas = [(inicio - L, "texto", f"Introdução gerada ({NOME_TEOR[info['teor']]})")]
    marcas += [(inicio - L + o, "dinamica", v) for o, v in info.get("dinamicas", [(0.0, info["dinamica"])])]
    marcas += [(inicio - L + a, "pedal", inicio - L + b) for a, b in info.get("pedal", [])]
    marcas += [(inicio, "texto", "Música"), (inicio, "dinamica", "mf")]
    return md, me, cf, marcas


def com_final(md, me, cf, final, k=0):
    """Põe o final gerado no compasso depois da última nota. Devolve (md, me, cifras, marcas)."""
    from introducao import NOME_TEOR
    f_md, f_me, f_cf, info = final
    fim = 4.0 * np.ceil(max(o + d for o, d, *_ in list(md) + list(me)) / 4 - 1e-6)
    md = list(md) + [(o + fim, d, [p + k for p in ps], *r) for o, d, ps, *r in f_md]
    me = list(me) + [(o + fim, d, [p + k for p in ps]) for o, d, ps in f_me]
    cf = list(cf) + [(o + fim, (r + k) % 12, t) for o, r, t in f_cf]
    marcas = [(fim, "texto", f"Final gerado ({NOME_TEOR[info['teor']]})")]
    marcas += [(fim + o, "dinamica", v) for o, v in info["dinamicas"]]
    if info.get("rit") is not None:
        marcas.append((fim + info["rit"], "texto", "rit."))
    if info.get("fermata") is not None:
        marcas.append((fim + info["fermata"], "fermata", None))
    marcas += [(fim + a, "pedal", fim + b) for a, b in info.get("pedal", [])]
    return md, me, cf, marcas


def carregar_transcricao(base: Path, audio: Path):
    """cache/transcricao.json da música, se for do mesmo áudio (tamanho e data); senão None."""
    arq = base / "cache" / "transcricao.json"
    if not arq.exists():
        print("[cache] sem transcrição guardada: gera do zero")
        return None
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except ValueError:
        return None
    st = audio.stat()
    if dados.get("audio_tamanho") != st.st_size or dados.get("audio_mtime_ns") != st.st_mtime_ns:
        print("[cache] transcrição é de outro áudio: gera do zero")
        return None
    if not dados.get("acordes") or not (dados.get("notas") or dados.get("leve")):   # o leve não tem melodia
        return None
    return dados


def _json_numpy(o):
    """json.dumps(default=...): números do numpy (alturas vindas das IAs) viram int/float."""
    if hasattr(o, "item"):
        return o.item()
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"{type(o).__name__} não vai pra JSON")


def deslocamento(md_ev, me_ev) -> float:
    """Tempos somados aos offsets pra partitura começar num compasso inteiro."""
    return float(-np.floor(min(e[0] for e in list(md_ev) + list(me_ev)) / 4) * 4)


def registrar_sincronia(base: Path, versao_nivel: str, grade, desloc: float):
    """cache/sincronia_original.json: batidas da gravação + deslocamento de cada versão.

    Posição na partitura (tempos) q -> segundos no original: interp(q - desloc, idx, bt).
    O visualizador usa isso pra acompanhar a gravação original, não só a prévia."""
    arq = base / "cache" / "sincronia_original.json"
    dados = {}
    if arq.exists():
        try:
            dados = json.loads(arq.read_text(encoding="utf-8"))
        except ValueError:
            dados = {}
    dados["bt"] = [round(float(x), 4) for x in grade.bt]
    dados["idx"] = [float(x) for x in grade.idx]
    dados.setdefault("versoes", {})[versao_nivel] = desloc
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(dados), encoding="utf-8")


def _suplementares(dn: int) -> int:
    """Linhas suplementares na clave de sol pela nota diatônica do music21 (Dó4 = 29, Mi4 = 31, Fá5 = 39)."""
    if dn >= 41:
        return (dn - 39) // 2
    if dn <= 29:
        return (31 - dn) // 2
    return 0


# 2026-11-11, 5 músicas × 3 níveis (regra antiga: 79 linhas 8va, 828 suplementares em cima):
# abrir 6 e nota embaixo da pauta dentro da 8va proibida (peso 100) -> 62 linhas, 624, nenhuma embaixo.
# Usuário: "escrever lá embaixo é tão ruim quanto lá em cima".
OITAVA_ABRIR = 6.0          # custo de abrir uma linha 8va (em linhas suplementares)
OITAVA_PESO_EMBAIXO = 100.0  # nota escrita embaixo da pauta DENTRO da 8va: na prática, proibida


def _oitava_acima(sc, abrir=None, min_notas=3, respiro=2.0, peso_embaixo=None):
    """Trecho agudo da mão direita vira 8va: escrito uma oitava abaixo, com a linha 8va.

    Programação dinâmica nas notas da direita em ordem de tempo: cada ataque fica normal ou em 8va;
    custo = linhas suplementares escritas (em cima e embaixo pesam igual: nota escrita lá embaixo
    é tão ruim de ler quanto lá em cima) + `abrir` por linha 8va nova (metade depois de pausa
    longa, lugar natural). Nota ligada fica no estado da que ataca. Linha com menos de
    `min_notas` ataques volta ao normal. As notas ficam na altura que soa: no MusicXML a altura é
    a sonora e o Verovio desenha uma oitava abaixo sob o octave-shift (até 2026-11-11 a nota era
    baixada aqui também e saía desenhada DUAS oitavas abaixo do que soa)."""
    from music21 import spanner
    direita = list(sc.parts)[0]
    notas = [n for n in direita.recurse().notes if n.__class__.__name__ in ("Note", "Chord")]
    notas.sort(key=lambda n: float(n.getOffsetInHierarchy(direita)))
    grupos = []   # [ataque + continuações ligadas]
    for n in notas:
        if grupos and n.tie is not None and n.tie.type in ("stop", "continue"):
            grupos[-1].append(n)
        else:
            grupos.append([n])
    if not grupos:
        return 0

    abrir = OITAVA_ABRIR if abrir is None else abrir
    peso_embaixo = OITAVA_PESO_EMBAIXO if peso_embaixo is None else peso_embaixo

    def custo(gr, s):
        c = 0.0
        for n in gr:
            for p in n.pitches:
                dn = p.diatonicNoteNum - 7 * s
                c += _suplementares(dn) * (peso_embaixo if s and dn <= 29 else 1.0)
        return c

    inicio = [float(g_[0].getOffsetInHierarchy(direita)) for g_ in grupos]
    fim = [float(g_[-1].getOffsetInHierarchy(direita)) + float(g_[-1].quarterLength) for g_ in grupos]
    INF = float("inf")
    melhor = [[custo(grupos[0], 0), custo(grupos[0], 1) + abrir]]
    volta = [[0, 0]]
    for k in range(1, len(grupos)):
        pausa = inicio[k] - fim[k - 1] > respiro + 1e-6
        abre = abrir / 2 if pausa else abrir
        linha, de = [], []
        for s in (0, 1):
            opcoes = [melhor[-1][0] + (abre if s == 1 else 0), melhor[-1][1]]
            ant = 0 if opcoes[0] <= opcoes[1] else 1
            linha.append(opcoes[ant] + custo(grupos[k], s))
            de.append(ant)
        melhor.append(linha)
        volta.append(de)
    s = 0 if melhor[-1][0] <= melhor[-1][1] else 1
    estado = [0] * len(grupos)
    for k in range(len(grupos) - 1, -1, -1):
        estado[k] = s
        s = volta[k][s]
    trechos, atual = [], []
    for k, st in enumerate(estado):
        if st:
            atual.append(k)
        elif atual:
            trechos.append(atual)
            atual = []
    if atual:
        trechos.append(atual)
    total = 0
    for t in trechos:
        if len(t) < min_notas:
            continue
        direita.insert(0, spanner.Ottava(grupos[t[0]][0], grupos[t[-1]][-1], type="8va", transposing=False))
        total += 1
    return total


def _marcas_nas_notas(sc, marcas, desloc):
    """Fermata nas notas que atacam no offset; pedal da 1ª à última nota da esquerda no trecho."""
    from music21 import expressions
    partes = list(sc.parts)
    for off, tipo, valor in marcas:
        o = off + desloc
        if tipo == "fermata":
            for parte in partes:
                for n in parte.recurse().notes:
                    if abs(float(n.getOffsetInHierarchy(parte)) - o) < 1e-6:
                        n.expressions.append(expressions.Fermata())
        elif tipo == "pedal" and len(partes) > 1:
            # linha de pedal (colchete). Termina na nota que abre o trecho seguinte: os colchetes
            # encadeados formam a linha com um entalhe em cada troca. Com "Ped. *" o asterisco
            # de soltar e o Ped. seguinte caíam um em cima do outro.
            esq = partes[1]
            todas = [(float(n.getOffsetInHierarchy(esq)), n) for n in esq.recurse().notes]
            fim = valor + desloc
            dentro = [n for t, n in todas if o - 1e-6 <= t < fim - 1e-6]
            if not dentro:
                continue
            depois = [n for t, n in todas if abs(t - fim) < 1e-6]
            pm = expressions.PedalMark(dentro[0], depois[0] if depois else dentro[-1])
            pm.pedalForm = expressions.PedalForm.Line
            pm.fim_q = fim          # pra prévia soltar o pedal na troca, não no fim da nota
            esq.insert(0, pm)


def montar_partitura(md_ev, me_ev, cifras, bpm: float, titulo: str, subtitulo: str, uma_armadura=False,
                     dedos_md=None, dedos_me=None, marcas=()):
    """md_ev / me_ev: (offset_em_tempos, duração, [midis]) sem sobreposição dentro da mão.
    cifras: (offset, root_pc, tipo). dedos_md/me: por evento, dedos na ordem de sorted(ps) ou None.
    marcas: (offset, "texto"|"dinamica", valor) na pauta de cima (ex.: "Introdução gerada", "p")."""
    from music21 import (articulations, chord, clef, dynamics, expressions, harmony, key, layout, meter,
                         metadata, note, pitch, stream, tempo)

    tudo = md_ev + me_ev
    if not tudo:
        sys.exit("nenhuma nota detectada")
    desloc = deslocamento(md_ev, me_ev)  # começa num compasso inteiro
    fim = max(e[0] + e[1] for e in tudo) + desloc
    # melodia manda; acordes da mão esquerda entram com peso menor (cada um soma 3 notas)
    if uma_armadura:  # nível fácil: armadura única, sem mudanças no meio
        mudancas = [(0.0, escolher_armadura([(e[1], e[2]) for e in md_ev] + [(0.3 * e[1], e[2]) for e in me_ev]))]
    else:
        from armaduras import inicios_de_frase
        mudancas = armaduras_por_trecho([(e[0] + desloc, e[1], e[2]) for e in md_ev]
                                        + [(e[0] + desloc, 0.3 * e[1], e[2]) for e in me_ev], fim,
                                        frases=inicios_de_frase([(e[0] + desloc, e[1]) for e in md_ev]))

    def sust_em(off):
        s_ = mudancas[0][1]
        for o, k_ in mudancas:
            if off >= o:
                s_ = k_
        return s_

    # grafia das notas do acorde vem da cifra (A7 = A C# E G, nunca D-)
    ativos = []
    for off, r, tipo in cifras:
        cs = acorde_com_grafia(r, TIPOS[tipo][1], sust_em(off + desloc))
        ativos.append((off + desloc, {q.pitchClass: q.name for q in cs.pitches}))

    # nota cromática fora do acorde: grafia pela direção da linha (sobe com #, desce com ♭)
    direcao = {}
    for eventos in (md_ev, me_ev):
        topos = sorted((e[0] + desloc, max(e[2])) for e in eventos if e[2])
        for (o1, m1), (o2, m2) in zip(topos, topos[1:]):
            if abs(m2 - m1) == 1 and o2 - o1 <= 2 + 1e-6:
                direcao[(round(o1, 6), m1)] = m2 - m1

    def P(m, off):
        if GRAFIA_ESCALA:
            nome = grafia_da_escala(sust_em(off)).get(m % 12)
            if nome is not None:   # nota da escala da armadura: sem acidente, nunca pela cifra
                q = pitch.Pitch(nome)
                q.octave = m // 12 - 1
                q.octave += (m - q.midi) // 12
                return q
        nomes_pc = {}
        for o, mapa in ativos:
            if o <= off + 1e-6:
                nomes_pc = mapa
            else:
                break
        nome = nomes_pc.get(m % 12)
        if nome is None:
            sus = sust_em(off)
            na_escala = {(7 * sus + k) % 12 for k in (0, 2, 4, 5, 7, 9, 11)}
            d = direcao.get((round(off, 6), m))
            if d and m % 12 not in na_escala:
                nome = (NOMES_PC_SUST if d > 0 else NOMES_PC_BEMOL)[m % 12]
            else:
                nome = nomes_para(sus)[m % 12]
        q = pitch.Pitch(nome)
        q.octave = m // 12 - 1
        q.octave += (m - q.midi) // 12  # B# / C- trocam de oitava
        return q

    md = stream.PartStaff(id="MD")
    me = stream.PartStaff(id="ME")
    for parte, cl in ((md, clef.TrebleClef()), (me, clef.BassClef())):
        parte.insert(0, cl)
        parte.insert(0, meter.TimeSignature("4/4"))
        for o, k_ in mudancas:
            parte.insert(o, key.KeySignature(k_))
    md.insert(0, tempo.MetronomeMark(number=round(bpm)))

    for parte, eventos, dedos in ((md, md_ev, dedos_md), (me, me_ev, dedos_me)):
        for i, (off, dur, ps, *resto) in enumerate(eventos):
            o = off + desloc
            el = note.Note(P(ps[0], o)) if len(ps) == 1 else chord.Chord([P(m, o) for m in sorted(ps)])
            el.quarterLength = dur
            if dedos and i < len(dedos) and dedos[i]:
                # acorde: o MusicXML distribui os dedos pelas notas na ordem (grave -> agudo)
                for f in dedos[i]:
                    el.articulations.append(articulations.Fingering(f))
            if resto and resto[0]:
                el.addLyric(resto[0])  # "tris-" / "-te-" / "-za" viram sílabas ligadas
            parte.insert(o, el)

    for off, tipo_marca, valor in marcas:
        o = off + desloc
        if tipo_marca in ("fermata", "pedal"):
            continue  # depois do makeNotation, nas notas já escritas
        if tipo_marca == "dinamica":
            md.insert(o, dynamics.Dynamic(valor))
            me.insert(o, dynamics.Dynamic(valor))
        else:
            te = expressions.TextExpression(valor)
            te.placement = "above"
            md.insert(o, te)

    simbolos = []
    for off, r, tipo in (cifras if MOSTRAR_CIFRAS else ()):
        o = off + desloc
        if o < 0:
            continue
        cs = acorde_com_grafia(r, TIPOS[tipo][1], sust_em(o))
        cs.writeAsChord = False
        simbolos.append((o, cs))

    sc = stream.Score()
    sc.metadata = metadata.Metadata()
    sc.metadata.title = titulo
    sc.metadata.composer = subtitulo
    sc.insert(0, md)
    sc.insert(0, me)
    sc.insert(0, layout.StaffGroup([md, me], symbol="brace", barTogether=True, name="Piano"))
    # as duas mãos até o mesmo compasso final: se a direita acaba antes, o último compasso
    # dela não existia (sem pausa) e as cifras desse trecho sumiam ou iam pra pauta de baixo
    fim_compasso = 4.0 * np.ceil((fim - 1e-6) / 4)
    for p in (md, me):
        p.makeRests(refStreamOrTimeRange=(0.0, fim_compasso), fillGaps=True, inPlace=True)
    sc = sc.makeNotation()
    # cifras só depois dos compassos montados: inserida antes, cifra que cai no meio de uma
    # nota conta como sobreposição e o music21 cria uma 2ª voz só de pausas na direita
    compassos = list(sc.parts[0].getElementsByClass(stream.Measure))
    for o, cs in simbolos:
        for m_ in compassos:
            if m_.offset - 1e-6 <= o < m_.offset + m_.duration.quarterLength - 1e-6:
                m_.insert(o - m_.offset, cs)
                _partir_pausa(m_, o - m_.offset)
                break
    _marcas_nas_notas(sc, marcas, desloc)
    _oitava_acima(sc)
    # nota dividida no compasso: o dedo fica só no ataque, não na continuação ligada
    for el in sc.recurse().notes:
        if el.tie is not None and el.tie.type in ("stop", "continue"):
            el.articulations = [a for a in el.articulations if not isinstance(a, articulations.Fingering)]
    # makeNotation põe bequadro nas cifras ("A♮m7"); cifra não leva acidente de armadura
    for cs in sc.recurse().getElementsByClass(harmony.ChordSymbol):
        for p_ in list(cs.pitches) + [cs.root(), cs.bass()]:
            if p_ is not None and p_.accidental is not None and p_.accidental.name == "natural":
                p_.accidental = None
    return sc, ", ".join(f"compasso {int(o // 4) + 1}: {k_:+d}" for o, k_ in mudancas)


def _partir_pausa(compasso, off: float):
    """Cifra no meio de uma pausa da direita: divide a pausa ali.

    Sem figura da pauta de cima naquele tempo o Verovio prende a cifra na pauta de baixo
    (G7 desenhado embaixo no compasso só de pausa). Pausa partida não cria voz nova.
    """
    from music21 import note
    for r in list(compasso.recurse().getElementsByClass(note.Rest)):
        ini = float(r.getOffsetBySite(r.activeSite))
        if ini + 1e-6 < off < ini + float(r.quarterLength) - 1e-6:
            dono = r.activeSite
            esq, dir_ = r.splitAtQuarterLength(off - ini)
            dono.remove(r)
            dono.insert(ini, esq)
            dono.insert(off, dir_)
            return


def _juntar_silabas(partes: list[str]) -> str | None:
    """["-da-", "-de"] -> "-dade";  ["que", "eu"] -> "que eu"."""
    if not partes:
        return None
    txt = partes[0]
    for p in partes[1:]:
        if txt.endswith("-") and p.startswith("-"):
            txt = txt[:-1] + p[1:]
        else:
            txt = txt.rstrip("-") + " " + p.lstrip("-")
    return txt


def _nota_com_silabas(ini: float, dur: float, midi: int, silabas: list[str]) -> list[tuple]:
    """Uma nota com várias sílabas vira notas repetidas na mesma altura (uma sílaba cada),
    como numa partitura de verdade, se couber na grade; senão as sílabas ficam juntas na nota."""
    passo = 1 / SR_GRADE
    cabem = int(round(dur / passo))
    m = min(len(silabas), cabem)
    if m <= 1:
        return [(ini, dur, [midi], _juntar_silabas(silabas))]
    base = max(1, cabem // m)  # em passos
    saida, pos = [], ini
    for j in range(m):
        d = base * passo if j < m - 1 else ini + dur - pos
        texto = _juntar_silabas(silabas[j:j + 1] if j < m - 1 else silabas[j:])
        saida.append((pos, d, [midi], texto))
        pos += d
    return saida


def juntar_repetidas(notas_q, letras, com_silaba=False, max_tempos=0.5):
    """Nota repetida colada na anterior vira uma nota sustentada só.

    Sem sílaba própria, a repetição é artefato (vibrato, consoante, corte no ataque da voz):
    sempre junta. com_silaba=True junta também a repetida curta (< max_tempos, as duas) que
    tem sílaba, e as sílabas ficam juntas na nota ("co-ra" -> "cora"); deixa menos ataques
    no piano, mas a letra perde uma nota por sílaba.
    Devolve (notas_q, letras, quantas juntou)."""
    saida, novas, juntou = [], {}, 0
    for i, n in enumerate(notas_q):
        sil = letras.get(i) or []
        if saida:
            ant = saida[-1]
            colada = abs(n[0] - ant[1]) < 1e-6 and n[2] == ant[2]
            curtas = (ant[1] - ant[0]) < max_tempos + 1e-6 and (n[1] - n[0]) < max_tempos + 1e-6
            if colada and (not sil or (com_silaba and curtas)):
                saida[-1] = (ant[0], n[1], ant[2], ant[3], n[4] if len(n) > 4 else ant[4])
                if sil:  # um texto só ("cora"), senão _nota_com_silabas dividiria a nota de novo
                    novas[len(saida) - 1] = [_juntar_silabas((novas.get(len(saida) - 1) or []) + list(sil))]
                juntou += 1
                continue
        saida.append(tuple(n))
        if sil:
            novas[len(saida) - 1] = list(sil)
    return saida, novas, juntou


def eventos_melodia_acordes(notas_q, acs, beats_por_janela=2, letras=None):
    """Converte melodia quantizada + acordes detectados em eventos das duas mãos + cifras.
    letras: {índice_da_nota: sílaba} (opcional)."""
    if not notas_q:
        raise ValueError("Nenhuma nota de melodia detectada na voz; não é possível gerar a partitura com melodia.")
    letras = letras or {}
    med = np.median([n[2] for n in notas_q])
    transp = 12 if med < 62 else 0  # melodia confortável na clave de sol
    md_ev = []
    for i, n in enumerate(notas_q):
        md_ev += _nota_com_silabas(n[0], n[1] - n[0], n[2] + transp, letras.get(i) or [])
    me_ev, cifras = [], []
    fim = max(n[1] for n in notas_q) + 4
    anterior = None
    for j, r, tipo, _ in acs:
        if r is None or j > fim:
            anterior = None
            continue
        if (r, tipo) != anterior:
            cifras.append((j, r, tipo))
        anterior = (r, tipo)
        ints = TIPOS[tipo][0]
        raiz = 40 + (r - 4) % 12  # fundamental entre E2 e D#3
        tons = [(r + ints[1]) % 12, (r + ints[-1]) % 12] if len(ints) == 4 else [(r + i) % 12 for i in ints[1:]]
        sup = [52 + (pc - 4) % 12 for pc in tons]  # 3ª e 7ª (ou 5ª) entre E3 e D#4
        me_ev.append((j, beats_por_janela, [raiz] + sup))
    return md_ev, me_ev, cifras


# ----------------------------------------------------------------------------- saída

def nome_pasta(titulo: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", titulo).strip() or "sem_titulo"


def copiar_original(audio: Path, pasta: Path):
    """Deixa o áudio de origem junto das partituras (mp3, pra não ocupar 50 MB de wav)."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / "Original.mp3"
    if not destino.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-b:a", "256k", str(destino)],
                       check=True)


PREVIAS_PENDENTES: list | None = None   # lista = prévias renderizadas no fim, em paralelo (main)


def renderizar_previas_pendentes(trabalhadores: int = 8):
    """Renderiza as prévias guardadas por salvar_versao, várias de uma vez (FluidSynth e ffmpeg
    são processos separados: os 16 núcleos ficavam parados com uma prévia por vez)."""
    global PREVIAS_PENDENTES
    fila, PREVIAS_PENDENTES = PREVIAS_PENDENTES or [], None
    if not fila:
        return
    print(f"[previas] gravando {len(fila)} prévias em áudio...", flush=True)   # o site marca a etapa por esta linha
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, min(trabalhadores, os.cpu_count() or 4, len(fila)))) as ex:
        list(ex.map(lambda par: midi_para_mp3(*par), fila))
    print(f"[previas] {len(fila)} prévias em {time.time() - t0:.0f} s")


def salvar_versao(sc, pasta: Path, versao: str, mid_previa: Path | None = None):
    """pasta/Versao.pdf + pasta/Versao - previa.mp3 + pasta/editaveis/Versao.musicxml|.mid"""
    ed = pasta / "editaveis"
    ed.mkdir(parents=True, exist_ok=True)
    xml, mid, pdf = ed / f"{versao}.musicxml", ed / f"{versao}.mid", pasta / f"{versao}.pdf"
    sc.write("musicxml", fp=str(xml))
    salvar_midi_notas(sc, mid, xml)
    n = xml_para_pdf(xml, pdf)
    if PREVIAS_PENDENTES is not None:
        PREVIAS_PENDENTES.append((mid_previa or mid, pasta / f"{versao} - previa.mp3"))
    else:
        midi_para_mp3(mid_previa or mid, pasta / f"{versao} - previa.mp3")
    print(f"[ok] {pdf} ({n} páginas)")


# destaque da melodia na prévia (só volume; a partitura não muda): nota cantada mais forte,
# nota de cima da direita sem letra um pouco mais forte, acompanhamento mais baixo
DESTAQUE = dict(cantada=+22, topo_direita=+8, resto_direita=-12, esquerda=-24)


def _velocidade_destaque(n, topos, base, sem_letra=False):
    mao = n['voz'].split(':')[-1]  # 'parte:voz:pauta'; pauta 1 = direita
    if mao != '1':
        d = DESTAQUE['esquerda']
    elif n.get('letra'):
        d = DESTAQUE['cantada']
    else:
        topo = (round(n['inicio'], 4), n['pitch']) in topos
        d = (DESTAQUE['cantada'] if sem_letra else DESTAQUE['topo_direita']) if topo else DESTAQUE['resto_direita']
    return int(min(127, max(25, base + d)))


def salvar_midi_notas(sc, destino: Path, xml: Path | None = None, destaque: bool = True):
    """Exporta somente notas escritas e respeita ligações parciais de acordes.

    destaque: melodia mais forte que o acompanhamento na prévia (DESTAQUE)."""
    import pretty_midi
    from music21 import converter, musicxml
    if sc is None:
        sc = converter.parse(str(xml))
    from sincronia import preparar_musicxml, notas_ligadas
    import xml.etree.ElementTree as ET
    texto=xml.read_text(encoding='utf-8') if xml else musicxml.m21ToXml.GeneralObjectExporter(sc).parse().decode('utf-8')
    _,segmentos=preparar_musicxml(texto)
    som=ET.fromstring(texto).find('.//sound[@tempo]')
    bpm=float(som.get('tempo')) if som is not None else 120
    pm=pretty_midi.PrettyMIDI(initial_tempo=bpm)
    # dinâmica escrita vira volume na prévia (pp..ff); sem marca, o volume de sempre (90)
    from music21 import dynamics as _din
    VEL={'pp':40,'p':55,'mp':70,'mf':85,'f':100,'ff':115}
    marcas_din=sorted({(float(d.getOffsetInHierarchy(sc))*60/bpm, VEL.get(d.value,90))
                       for d in sc.recurse().getElementsByClass(_din.Dynamic)})
    def velocidade(t):
        v=90
        for tm,vel in marcas_din:
            if tm<=t+1e-6:
                v=vel
        return v
    instrumentos={}
    ligadas=notas_ligadas(segmentos)
    topos={}
    for n in ligadas:  # nota mais aguda de cada ataque da direita
        if n['voz'].split(':')[-1]=='1':
            k=round(n['inicio'],4); topos[k]=max(topos.get(k,0),n['pitch'])
    topos={(k,p) for k,p in topos.items()}
    sem_letra=not any(n.get('letra') for n in ligadas)   # arranjo da IA: a voz de cima é a melodia
    for n in ligadas:
        inst=instrumentos.setdefault(n['voz'],pretty_midi.Instrument(program=0,name=n['voz']))
        v=velocidade(n['inicio'])
        if destaque:
            v=_velocidade_destaque(n,topos,v,sem_letra)
        inst.notes.append(pretty_midi.Note(velocity=v,pitch=n['pitch'],start=n['inicio'],end=n['fim']))
    # pedal escrito vira sustain (CC64) na prévia, em todos os canais
    from music21 import expressions as _expr
    for pm_ in sc.recurse().getElementsByClass(_expr.PedalMark):
        ns_=list(pm_.getSpannedElements())
        if not ns_:
            continue
        ini_=float(ns_[0].getOffsetInHierarchy(sc))*60/bpm
        fim_q=getattr(pm_,'fim_q',None)
        fim_=(fim_q if fim_q is not None else
              float(ns_[-1].getOffsetInHierarchy(sc))+float(ns_[-1].quarterLength))*60/bpm
        for inst in instrumentos.values():
            inst.control_changes.append(pretty_midi.ControlChange(64,127,ini_+.01))
            inst.control_changes.append(pretty_midi.ControlChange(64,0,max(ini_+.02,fim_-.02)))
    pm.instruments=list(instrumentos.values())
    pm.write(str(destino))


def achar_chrome() -> str:
    for n in ["google-chrome", "chromium", "msedge", "chrome"]:
        if p := shutil.which(n):
            return p
    for p in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]:
        if os.path.exists(p):
            return p
    sys.exit("Chrome/Edge não encontrado para gerar o PDF")


_MOJIBAKE = None


def _desembaralhar(svg: str) -> str:
    """Verovio no Windows às vezes devolve UTF-8 lido como cp1252 ("â€“" no lugar de "–")."""
    import re
    global _MOJIBAKE
    if _MOJIBAKE is None:
        alta = "".join(bytes([b]).decode("cp1252", "ignore") for b in range(0x80, 0xC0))
        _MOJIBAKE = re.compile(f"[Â-ô][{re.escape(alta)}]{{1,3}}")

    def conserta(m):
        t = m.group(0)
        for n in range(len(t), 1, -1):  # a sequência pode ter "sobra" colada (ex.: espaço duro)
            try:
                return t[:n].encode("cp1252").decode("utf-8") + t[n:]
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        return t
    return _MOJIBAKE.sub(conserta, svg)


_RE_CHAR_JA = re.compile("[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_RE_LETRA_JA = re.compile(r"(<lyric\b[^>]*>(?:(?!</lyric>).)*?<text[^>]*>)([^<]*[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff][^<]*)(</text>)", re.S)


def espacar_kana(texto: str) -> str:
    """O Verovio mede kana/kanji como letra latina (metade da largura real) e espreme a letra.

    Um espaço duro de cada lado por caractere japonês reserva a largura que falta, com a
    sílaba centrada na nota. Só no desenho: o MusicXML salvo fica com a letra limpa.
    """
    def pad(m):
        n = len(_RE_CHAR_JA.findall(m.group(2)))
        return m.group(1) + "\u00a0" * n + m.group(2).strip() + "\u00a0" * n + m.group(3)
    return _RE_LETRA_JA.sub(pad, texto)


def xml_para_verovio(texto: str) -> str:
    """Verovio não aceita layer zero; renumerar sem alterar conteúdo musical. Kana espaçado."""
    texto = espacar_kana(texto)
    if '<voice>0</voice>' not in texto:
        return texto
    import xml.etree.ElementTree as ET
    raiz=ET.fromstring(texto)
    for voz in raiz.iter('voice'):
        if voz.text and voz.text.isdigit():
            voz.text=str(int(voz.text)+1)
    return ET.tostring(raiz,encoding='unicode')


# Verovio só põe dedilhado em cima/embaixo da nota; com isto ele grava a nota de cada número
# spacingSystem: o Verovio não conta a linha de pedal na colisão; com o mínimo padrão (4)
# ela batia nas cifras do sistema de baixo
OPCOES_DEDOS = {"svgAdditionalAttribute": ["fing@startid"], "fingeringScale": 0.6, "spacingSystem": 12}

_RE_NOTA = re.compile(r'<g id="([^"]+)" class="note">')
_RE_CABECA = re.compile(r'class="notehead">\s*<use xlink:href="#(E0[0-9A-F]{2})?[^"]*"[^>]*transform="translate\((-?[\d.]+),\s*(-?[\d.]+)\)')
_RE_ACID = re.compile(r'class="accid">\s*<use [^>]*transform="translate\((-?[\d.]+),\s*(-?[\d.]+)\)')
_RE_DEDO = re.compile(r'(<g id="[^"]+" class="fing" data-startid="#([^"]+)">\s*<text )x="(-?[\d.]+)" y="(-?[\d.]+)" '
                      r'text-anchor="middle"(.*?</g>)', re.S)
# largura da cabeça em espaços de pauta (SMuFL) e espaço de pauta no SVG do Verovio (glifo em scale 0.72)
_LARG_CABECA = {"E0A2": 1.69, "E0A3": 1.18, "E0A4": 1.18}
_ESPACO = 180.0


def dedos_ao_lado(svg: str) -> str:
    """Leva cada número de dedo pro lado da cabeça da sua nota.

    Esquerda (antes do acidente) por padrão; acorde com segunda (cabeça vizinha colada à
    esquerda), passa pra esquerda dela. Se ali houver clave/armadura/fórmula de compasso
    (primeira nota do sistema), vai pra direita da cabeça, se não bater em nota, acidente ou
    barra; só com os dois lados ocupados fica em cima. Em cima da nota os números
    empilham e ocupam espaço vertical (pedido do usuário)."""
    pos, cabecas, esquerda_da_nota = {}, [], []   # esquerda_da_nota: (x da cabeça, y, x do acidente ou da cabeça)
    marcas = list(_RE_NOTA.finditer(svg))
    for i, m in enumerate(marcas):
        trecho = svg[m.end(): marcas[i + 1].start() if i + 1 < len(marcas) else m.end() + 4000]
        c = _RE_CABECA.search(trecho)
        if not c:
            continue
        hx, hy = float(c.group(2)), float(c.group(3))
        hw = _LARG_CABECA.get(c.group(1), 1.2) * _ESPACO
        a = _RE_ACID.search(trecho)
        pos[m.group(1)] = (float(a.group(1)) if a else hx, hx, hy, hw)
        cabecas.append((hx, hw, hy))
        esquerda_da_nota.append((hx, hy, float(a.group(1)) if a else hx))
        if a:
            cabecas.append((float(a.group(1)), .8 * _ESPACO, float(a.group(2))))
    barras = []
    for grupo in re.findall(r'class="barLine[^"]*">(.*?)</g>', svg, re.S):
        barras += [(float(x), min(float(y1), float(y2)), max(float(y1), float(y2)))
                   for x, y1, y2 in re.findall(r'<path d="M(-?[\d.]+) (-?[\d.]+) L-?[\d.]+ (-?[\d.]+)"', grupo)]

    # clave, armadura e fórmula de compasso: à esquerda delas o número não cabe
    cabecalho = []
    for m in re.finditer(r'class="(clef|keySig|meterSig)"', svg):
        trecho = svg[m.end(): m.end() + 1500]
        corte = re.search(r'class="(?!keyAccid)', trecho)
        trecho = trecho[:corte.start()] if corte else trecho
        cabecalho += [(float(a), float(b)) for a, b in re.findall(r'translate\((-?[\d.]+),\s*(-?[\d.]+)\)', trecho)]

    colocados = []   # (ini, fim, y) dos dedos já postos ao lado: um não pode cair em cima do outro

    def mover(m):
        alvo = pos.get(m.group(2))
        if not alvo:
            return m.group(0)
        tams = [float(t) for t in re.findall(r'font-size="(\d+)px"', m.group(5)) if float(t) > 0]
        fs = max(tams) if tams else 250.0   # o <text> externo vem com 0px; o tamanho real é o do tspan
        x, hx, y, hw = alvo
        digitos = "".join(re.findall(r">\s*(\d+)\s*<", m.group(5)))
        largura = .7 * fs * max(1, len(digitos))
        base_y = f'y="{y + .36 * fs:.0f}"'

        def no_cabecalho(ini, fim):
            return any(gx - 50 < fim and ini < gx + 420 and abs(gy - y) < 900 for gx, gy in cabecalho)

        def livre_de_dedos(ini, fim):
            return not any(a < fim + 20 and ini < b + 20 and abs(cy - y) < .7 * fs for a, b, cy in colocados)   # terça (1 espaço) empilha; segunda não

        def pronto(ini, fim, texto):
            colocados.append((ini, fim, y))
            return texto

        direita = x - .25 * fs
        # acorde com segunda: a cabeça vizinha do mesmo acorde fica do outro lado da haste, colada à
        # esquerda (meio espaço acima/abaixo). O dedo passa pra esquerda dela, com lugar pro dedo dela.
        vizinhas = [ex for ox, oy, ex in esquerda_da_nota          # ex: onde começa a vizinha (acidente incluso)
                    if hx - 1.3 * hw <= ox < hx - 1 and 1 < abs(oy - y) <= .6 * _ESPACO]
        if vizinhas:
            direita = min(vizinhas) - .25 * fs - largura - 30
        if not no_cabecalho(direita - largura, direita) and livre_de_dedos(direita - largura, direita):
            return pronto(direita - largura, direita,
                          f'{m.group(1)}x="{direita:.0f}" {base_y} text-anchor="end"{m.group(5)}')
        # esquerda ocupada (começo do sistema ou outro dedo): tenta a direita da cabeça
        ini = hx + hw + .2 * fs
        fim = ini + largura
        bate = any(ox < fim + 40 and ox + ow > ini and abs(oy - y) < 1.4 * _ESPACO and not (ox == hx and oy == y)
                   for ox, ow, oy in cabecas)
        bate = bate or any(ini - 20 < bx < fim + 40 and y1 - 100 < y < y2 + 100 for bx, y1, y2 in barras)
        if not bate and livre_de_dedos(ini, fim):
            return pronto(ini, fim, f'{m.group(1)}x="{ini:.0f}" {base_y} text-anchor="start"{m.group(5)}')
        # os dois lados ocupados: fica em cima da nota (onde o Verovio pôs); se bater em outro dedo, sobe
        orig = re.search(r'x="(-?[\d.]+)" y="(-?[\d.]+)"', m.group(0))
        if not orig:
            return m.group(0)
        ox_, oy_ = float(orig.group(1)), float(orig.group(2))
        ini, fim = ox_ - largura / 2, ox_ + largura / 2
        for _ in range(4):
            y_salvo = y
            y = oy_ - .36 * fs              # livre_de_dedos compara pela linha de base da nota
            if livre_de_dedos(ini, fim):
                break
            oy_ -= .8 * fs
            y = y_salvo
        colocados.append((ini, fim, oy_ - .36 * fs))
        return m.group(0).replace(orig.group(0), f'x="{ox_:.0f}" y="{oy_:.0f}"', 1)
    return _RE_DEDO.sub(mover, svg)


_RE_PEDAL = re.compile(r'<g id="[^"]+" class="pedal">(.*?)</g>', re.S)
_RE_RET = re.compile(r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" height="([\d.]+)" width="([\d.]+)" */>')


def pedal_continuo(svg: str, encosta: float = 260.0) -> str:
    """Colchetes de pedal encostados viram uma linha só com entalhe "^" em cada troca.

    O Verovio desenha cada trecho de pedal como um colchete; na troca o fim de um e o começo
    do seguinte caem juntos ("||", linhas sobrepostas), e o "bounce" do MEI ele não desenha."""
    sistemas = [m.start() for m in re.finditer(r'<g id="[^"]+" class="system">', svg)]
    if not sistemas or "class=\"pedal\"" not in svg:
        return svg
    partes = [svg[:sistemas[0]]]
    limites = sistemas + [len(svg)]
    for a, b in zip(limites, limites[1:]):
        bloco = svg[a:b]
        colchetes = []
        for m in _RE_PEDAL.finditer(bloco):
            rets = [tuple(float(v) for v in r) for r in _RE_RET.findall(m.group(1))]
            if not rets:
                continue
            horiz = [r for r in rets if r[3] > r[2]]
            vert = [r for r in rets if r[2] > r[3]]
            y = max((r[1] for r in horiz), default=max(r[1] for r in rets))
            topo = min((r[1] for r in vert), default=y - 160)
            espessura = min((r[2] for r in horiz), default=18.0)
            colchetes.append([min(r[0] for r in rets), max(r[0] + r[3] for r in rets), y, topo, espessura])
        if len(colchetes) < 2:
            partes.append(bloco)
            continue
        colchetes.sort()
        linhas, atual = [], [colchetes[0]]
        for c in colchetes[1:]:
            if c[0] - atual[-1][1] <= encosta and abs(c[2] - atual[-1][2]) < 60:
                atual.append(c)
            else:
                linhas.append(atual)
                atual = [c]
        linhas.append(atual)
        caminhos = []
        for ln in linhas:
            y = max(c[2] for c in ln) + ln[0][4] / 2
            topo = min(c[3] for c in ln)
            alt = y - topo
            x0, x1 = ln[0][0] + ln[0][4] / 2, ln[-1][1] - ln[0][4] / 2
            d = f"M{x0:.0f} {topo:.0f} L{x0:.0f} {y:.0f}"
            for c in ln[1:]:
                xc = c[0] + c[4] / 2
                d += f" L{xc - alt * .6:.0f} {y:.0f} L{xc:.0f} {y - alt * .9:.0f} L{xc + alt * .6:.0f} {y:.0f}"
            d += f" L{x1:.0f} {y:.0f} L{x1:.0f} {topo:.0f}"
            caminhos.append(f'<path d="{d}" fill="none" stroke="currentColor" stroke-width="{ln[0][4]:.0f}" />')
        bloco = _RE_PEDAL.sub("", bloco)
        fim = bloco.rfind("</g>")
        bloco = bloco[:fim] + '<g class="pedal">' + "".join(caminhos) + "</g>" + bloco[fim:]
        partes.append(bloco)
    return "".join(partes)


def xml_para_pdf(xml: Path, pdf: Path):
    import verovio
    verovio.enableLog(False)
    tk = verovio.toolkit()
    tk.setResourcePath(str(Path(verovio.__file__).parent / 'data'))
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 42,
                   "pageMarginTop": 80, "pageMarginBottom": 80,
                   "pageMarginLeft": 80, "pageMarginRight": 80,
                   "adjustPageHeight": False, "footer": "none", "breaks": "auto", **OPCOES_DEDOS})
    if not tk.loadData(xml_para_verovio(xml.read_text(encoding="utf-8"))):  # loadFile falha com acento no caminho (Windows)
        raise RuntimeError(f"Verovio não conseguiu ler o MusicXML: {xml}")
    pags = [pedal_continuo(dedos_ao_lado(_desembaralhar(tk.renderToSVG(i)))) for i in range(1, tk.getPageCount() + 1)]
    import html as _h
    titulo_pdf = _h.escape(f"{pdf.parent.name} — {pdf.stem}")  # nome que o visualizador de PDF mostra
    html = [f"<!doctype html><meta charset='utf-8'><title>{titulo_pdf}</title><style>@page{{size:A4;margin:0}}"
            "body{margin:0}.p{width:210mm;height:297mm;page-break-after:always;overflow:hidden}"
            ".p svg{width:100%;height:100%}</style>"]
    html += [f"<div class='p'>{s}</div>" for s in pags]
    fd, nome = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    h = Path(nome)
    h.write_text("".join(html), encoding="utf-8")
    try:
        subprocess.run([achar_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf.resolve()}", h.as_uri()],
                       capture_output=True, timeout=180, check=True)
        if not pdf.exists() or pdf.stat().st_size < 100:
            raise RuntimeError(f"Chrome não produziu o PDF: {pdf}")
    finally:
        h.unlink(missing_ok=True)
    return len(pags)


def _fluidsynth() -> str | None:
    if p := shutil.which("fluidsynth"):
        return p
    achados = sorted((AQUI / "ferramentas").glob("fluidsynth*/**/bin/fluidsynth.exe"))
    return str(achados[-1]) if achados else None


def _soundfont() -> Path | None:
    sf = AQUI / "soundfonts" / "piano.sf2"
    return sf if sf.exists() else None


def midi_para_mp3(mid: Path, mp3: Path):
    """Prévia audível: piano de cauda de verdade (FluidSynth + SoundFont Steinway em soundfonts/piano.sf2).
    Sem FluidSynth/SoundFont, cai no sintetizador simples."""
    fs, sf2 = _fluidsynth(), _soundfont()
    if not (fs and sf2):
        return _midi_para_mp3_simples(mid, mp3)
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(mid))
    for inst in pm.instruments:  # tudo no piano acústico, dinâmica mais suave (som doce)
        inst.program, inst.is_drum = 0, False
        for n in inst.notes:
            fator = 0.72 if n.pitch >= 60 else 0.8
            n.velocity = int(np.clip(n.velocity * fator, 30, 100))
    tmp_mid = mp3.with_name(f"_tmp_{mp3.stem}.mid")   # nome por prévia: elas rodam em paralelo
    wav = mp3.with_name(f"_tmp_{mp3.stem}.wav")
    pm.write(str(tmp_mid))
    subprocess.run([fs, "-ni", "-q", "-g", "0.8", "-r", "44100",
                    "-o", "synth.reverb.active=1", "-o", "synth.reverb.room-size=0.6",
                    "-o", "synth.reverb.level=0.35",
                    "-F", str(wav), str(sf2), str(tmp_mid)], check=True, capture_output=True)
    # volume: ganho calculado (RMS dos trechos com som ~ -18 dBFS, pico <= -1,5 dB). Era o loudnorm
    # do ffmpeg, que sozinho levava mais tempo que a síntese inteira
    import soundfile as sf
    y, _ = sf.read(str(wav), dtype="float32")
    y = y.mean(axis=1) if y.ndim > 1 else y
    quadros = np.abs(y[: len(y) // 2205 * 2205]).reshape(-1, 2205) if len(y) >= 2205 else np.abs(y)[None]
    rms_q = np.sqrt((quadros ** 2).mean(axis=1))
    ativos = rms_q[rms_q > max(1e-4, rms_q.max() * .05)]
    rms = float(np.sqrt((ativos ** 2).mean())) if len(ativos) else 1e-3
    pico = float(np.abs(y).max()) or 1.0
    ganho = min(10 ** (-18 / 20) / max(rms, 1e-6), 10 ** (-1.5 / 20) / pico)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                    "-af", f"volume={ganho:.4f}", "-b:a", "192k", str(mp3)], check=True)
    wav.unlink(missing_ok=True)
    tmp_mid.unlink(missing_ok=True)


def _midi_para_mp3_simples(mid: Path, mp3: Path):
    """Sintetizador de emergência (senoides) quando não há FluidSynth."""
    import pretty_midi
    import soundfile as sf
    pm = pretty_midi.PrettyMIDI(str(mid))
    sr = 22050
    y = np.zeros(int((pm.get_end_time() + 2) * sr))
    for inst in pm.instruments:
        for n in inst.notes:
            f = 440 * 2 ** ((n.pitch - 69) / 12)
            d = min(n.end - n.start, 3.0) + 0.3
            t = np.arange(int(d * sr)) / sr
            env = np.exp(-t * 3.0) * np.minimum(1, t * 200)
            onda = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t)
                    + 0.15 * np.sin(6 * np.pi * f * t)) * env * (n.velocity / 127)
            i = int(n.start * sr)
            y[i:i + len(onda)] += onda[:len(y) - i]
    y = 0.9 * y / (np.abs(y).max() + 1e-9)
    wav = mp3.with_suffix(".wav")
    sf.write(wav, y, sr)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "160k", str(mp3)], check=True)
    wav.unlink()


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path, nargs="?", help="música (wav/mp3); dispensável com --do-karaoke")
    ap.add_argument("--do-karaoke", default=None, metavar="MUSICA",
                    help="usa uma música do karaokê (slug ou pasta): voz e acompanhamento já separados e a letra já alinhada")
    ap.add_argument("--sem-alinhamento", action="store_true",
                    help="não alinha a letra oficial com o alinhador do karaokê (fica só Whisper + correção de grafia)")
    ap.add_argument("--saida", type=Path, default=AQUI / "saida")
    ap.add_argument("--titulo", default=None)
    ap.add_argument("--pasta", default=None, help="nome da pasta em saida/ (padrão: o título)")
    ap.add_argument("--subtitulo", default="Transcrição automática para piano")
    ap.add_argument("--pop2piano", action="store_true", help="gera também o arranjo do Pop2Piano")
    ap.add_argument("--estilo", type=int, default=1, choices=range(1, 22), metavar="1-21",
                    help="estilo do Pop2Piano (composer1..21): 12 = mais baixo, 8 = mais acordes, 21 = mais leve")
    ap.add_argument("--amtapc", action="store_true",
                    help="gera também o arranjo do AMT-APC (IA de piano cover; precisa de modelos/amt-apc)")
    ap.add_argument("--sem-letra", action="store_true", help="não coloca a letra embaixo das notas")
    ap.add_argument("--letra", type=Path, default=None,
                    help="letra oficial (.txt) pra corrigir a grafia do que o Whisper ouviu")
    ap.add_argument("--artista", default=None, help="artista (pra buscar a letra oficial; padrão: começo do subtítulo)")
    ap.add_argument("--sem-busca-letra", action="store_true", help="não busca a letra oficial no LRCLIB")
    ap.add_argument("--idioma", default="pt", help="pt, en, es... ou auto (Whisper detecta)")
    ap.add_argument("--hibrido", action="store_true",
                    help="gera também melodia cantada + acompanhamento do Pop2Piano na mão esquerda")
    ap.add_argument("--nivel", default="medio",
                    help="dificuldade: facil, medio, dificil ou lista (facil,medio,dificil) ou 'todos'")
    ap.add_argument("--dedos", default="auto", choices=("auto", "todos", "mudancas", "nenhum"),
                    help="números dos dedos na partitura (auto: todos no fácil, só nas mudanças de posição no resto)")
    ap.add_argument("--sem-maos", action="store_true",
                    help="não corrige trechos que a mão não alcança (só calcula os dedos)")
    ap.add_argument("--grave-embolado", action="store_true",
                    help="não tira da esquerda a voz que embola no grave (terça abaixo de Dó3; comportamento antigo)")
    ap.add_argument("--introducao", default=None, choices=("calma", "lenta", "emotiva", "animada", "epica"),
                    help="acrescenta uma introdução gerada (não existe na gravação) com esse teor, feita do refrão")
    ap.add_argument("--final", default=None, choices=("calma", "lenta", "emotiva", "animada", "epica"),
                    help="acrescenta um final gerado (não existe na gravação) com esse teor")
    ap.add_argument("--separador", default="htdemucs", choices=("htdemucs", "htdemucs_6s"),
                    help="modelo do Demucs; htdemucs_6s separa também guitarra e piano (acordes com eles)")
    ap.add_argument("--reusar-cache", action="store_true",
                    help="usa a transcrição guardada (cache/transcricao.json) e só escreve as partituras de novo")
    ap.add_argument("--escrita-ja", default="romaji", choices=("romaji", "kana"),
                    help="letra em japonês embaixo das notas: romaji (padrão) ou kana")
    ap.add_argument("--acompanhamento", default=None, choices=("calma", "lenta", "emotiva", "animada", "epica"),
                    help="mão esquerda da música inteira (versão Acordes) na textura desse teor")
    ap.add_argument("--variacao", type=int, default=0, help="outra versão da introdução gerada (0 = padrão)")
    ap.add_argument("--sem-transpor", action="store_true", help="no nível fácil, não transpõe pra tom sem acidentes")
    ap.add_argument("--tom-ia-cru", action="store_true",
                    help="não corrige nota fora do tom no arranjo da IA (tonalidade.py)")
    ap.add_argument("--leve", action="store_true",
                    help="só o AMT-APC, sem separar a voz, sem melodia e sem letra (sem Demucs/CREPE/Whisper): "
                         "batidas e acordes da própria mistura. Roda só em CPU (~1,5 min por música)")
    ap.add_argument("--cifras", action="store_true", help="desenha o nome dos acordes em cima da pauta (padrão: sem)")
    ap.add_argument("--batidas-librosa", action="store_true",
                    help="modo leve: batidas do librosa e tempo 1 pela heurística (sem madmom; comportamento antigo)")
    ap.add_argument("--acordes", default="ambos", choices=("mistura", "ia", "ambos"),
                    help="modo leve: acordes pelo croma da gravação, pelas notas do AMT-APC ou pelos dois "
                         "(padrão; 64 músicas: choques do difícil −31%%, acidentes −22%%)")
    ap.add_argument("--dinamica", action="store_true",
                    help="modo leve: escreve p/mp/mf/f pela intensidade da gravação (dinamica.py)")
    ap.add_argument("--sem-repeticoes", action="store_true",
                    help="modo leve: não escreve igual os trechos que se repetem (repeticoes.py)")
    ap.add_argument("--sem-ajuste", action="store_true",
                    help="modo leve: não aplica a tocabilidade por regra (tocavel.py: síncopes, oitavas da esquerda)")
    ap.add_argument("--versoes", default="",
                    help="só escreve estas versões (ex.: AMT-APC ou AMT-APC,HibridoAMT); vazio = todas as calculadas")
    ap.add_argument("--derivar", action="store_true",
                    help="(padrão) fácil e difícil derivados do médio (derivados.py): fácil simplifica, difícil "
                         "enriquece (arpejos, 3ª/6ª, oitavas, pedal, fermata)")
    ap.add_argument("--sem-derivar", action="store_true",
                    help="fácil e difícil transcritos cada um no seu nível (comportamento antigo)")
    ap.add_argument("--repetidas", action="store_true",
                    help="mantém as notas repetidas coladas sem sílaba (comportamento antigo)")
    ap.add_argument("--juntar-silabas", action="store_true",
                    help="junta também repetida curta com sílaba (as sílabas ficam na mesma nota)")
    ap.add_argument("--melodia-crua", action="store_true",
                    help="não corrige afinação nem puxa pra escala as notas duvidosas da voz (afinacao.py)")
    ap.add_argument("--gravado", action="store_true",
                    help="versão Híbrido Gravado: esquerda com o piano e o violão transcritos da gravação "
                         "(6 faixas + Kong/Basic Pitch; ver gravado.py)")
    ap.add_argument("--facil-fiel", action="store_true",
                    help="nível fácil com a melodia do médio (grade de 1/2 tempo, sem tirar passagens nem "
                         "cromatismos, no tom original); só a mão esquerda fica fácil")
    args = ap.parse_args()
    args.derivar = not args.sem_derivar   # revisão às cegas 2026-11-10: derivar do médio ficou "infinitamente melhor"
    global MOSTRAR_CIFRAS
    MOSTRAR_CIFRAS = args.cifras
    import letra as _letra
    _letra.ESCRITA_JA = args.escrita_ja
    global SR_GRADE, PREVIAS_PENDENTES
    from niveis import NIVEIS
    niveis = list(NIVEIS) if args.nivel == "todos" else [n.strip() for n in args.nivel.split(",")]
    for n in niveis:
        if n not in NIVEIS:
            ap.error(f"nível inválido: {n} (use {', '.join(NIVEIS)})")

    import librosa
    karaoke = None
    if args.do_karaoke:
        from alinhamento import musica_do_karaoke, pasta_do_karaoke
        karaoke = musica_do_karaoke(pasta_do_karaoke(args.do_karaoke), AQUI / "trabalho")
        audio = karaoke["audio"].resolve()
        args.titulo = args.titulo or karaoke["titulo"]
        args.artista = args.artista or karaoke["artista"]
        args.idioma = karaoke["idioma"]
        print(f"[karaoke] {karaoke['titulo']} de {karaoke['artista']} ({args.idioma}); "
              f"letra {'já alinhada' if karaoke['palavras'] else 'será alinhada de novo'}")
    elif args.audio is None:
        ap.error("informe o áudio ou --do-karaoke")
    else:
        audio = args.audio.resolve()
    titulo = args.titulo or audio.stem.replace("_", " ").title()
    args.saida.mkdir(parents=True, exist_ok=True)
    base = args.saida / (args.pasta or nome_pasta(titulo))  # uma pasta por música
    copiar_original(audio, base)

    reuso = carregar_transcricao(base, audio) if getattr(args, "reusar_cache", False) else None
    if reuso and reuso.get("leve") and not getattr(args, "leve", False):
        reuso = None   # cache do modo leve não tem melodia nem letra: o completo gera do zero
    if reuso:
        # só a escrita da partitura: melodia, acordes, batidas e letra do cache (sem Demucs/Whisper)
        bt, fase, bpm = np.array(reuso["bt"]), int(reuso["fase"]), float(reuso["bpm"])
        grade = Grade(bt, fase)
        notas = [tuple(n) for n in reuso["notas"]]
        acs = [tuple(a) for a in reuso["acordes"]]
        # a fase do madmom já separa o 1 do 3: a heurística da troca de acorde só vale pras outras grades
        fase, acs, mudou = (fase, acs, False) if reuso.get("batidas") == "madmom" else corrigir_fase(fase, acs)
        if mudou:   # cache anterior à correção: compassos meio compasso deslocados
            grade = Grade(bt, fase)
            print(f"[batidas] tempo 1 corrigido pela harmonia: batida {fase}")
        if reuso.get("leve") and reuso.get("fonte_acordes", "mistura") != args.acordes:
            # outra fonte de acordes: recalcula só os acordes (as batidas do cache ficam)
            from amtapc import midi_amtapc
            from scipy.signal import butter, sosfiltfilt
            sr = 22050
            mix = carregar(audio, sr)
            baixo = sosfiltfilt(butter(4, 200, "low", fs=sr, output="sos"), mix).astype(np.float32)
            acs = acordes(mix, baixo, sr, grade, midi_arranjo=midi_amtapc(audio, base, "medio"), fonte=args.acordes)
            print(f"[acordes] recalculados com a fonte '{args.acordes}'")
        palavras = [tuple(p) for p in reuso.get("palavras") or []]
        diagnostico = reuso.get("diagnostico") or {}
        args.idioma = reuso.get("idioma") or args.idioma
        print(f"[cache] reusando transcrição: {len(notas)} notas, {len(acs)} janelas de acorde, "
              f"{len(palavras)} palavras (sem separar nem transcrever de novo)")
    elif getattr(args, "leve", False):
        # modo leve: nada de voz/melodia/letra. Batidas e acordes da mistura; o grave por passa-baixa
        from scipy.signal import butter, sosfiltfilt
        sr = 22050
        mix = carregar(audio, sr)
        baixo = sosfiltfilt(butter(4, 200, "low", fs=sr, output="sos"), mix).astype(np.float32)
        print("[batidas] detectando pulso (modo leve, da mistura)...")
        madmom = None if getattr(args, "batidas_librosa", False) else batidas_madmom(audio, len(mix) / sr)
        if madmom:
            bt, bpm, fase_m, por_compasso = madmom
            if por_compasso != 4:
                print(f"[batidas] AVISO: compasso de {por_compasso} tempos detectado; a partitura ainda sai em 4/4")
        else:
            bt, bpm = batidas(mix, sr, mix)
        from amtapc import midi_amtapc   # o arranjo sai de qualquer jeito: o grave dele dá o tempo 1
        # As batidas do librosa vêm ~40 ms depois dos ataques (os do AMT-APC e as batidas do madmom
        # concordam); deslocar a grade do librosa piorava (HISTORICO §38), trocar pelo madmom melhora (§42).
        mid_arranjo = midi_amtapc(audio, base, "medio" if args.derivar else niveis[0])
        fase = fase_m if madmom else fase_pelo_midi(bt, mid_arranjo)
        grade = Grade(bt, fase)
        print(f"[batidas] ~{bpm:.0f} bpm, {len(bt)} batidas, tempo 1 na batida {fase}"
              f" ({'madmom' if madmom else 'librosa + graves do arranjo'})")
        print("[acordes] detectando harmonia (modo leve, da mistura)...")
        acs = acordes(mix, baixo, sr, grade, midi_arranjo=mid_arranjo, fonte=args.acordes)
        if not madmom:   # a heurística da troca de acorde só pra grade do librosa (não separa o 1 do 3)
            fase, acs, mudou = corrigir_fase(fase, acs)
            if mudou:
                grade = Grade(bt, fase)
                print(f"[batidas] tempo 1 corrigido pela harmonia: batida {fase}")
        notas, palavras, diagnostico = [], [], None
        cache = base / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "transcricao.json").write_text(json.dumps(dict(
            audio=str(audio), audio_tamanho=audio.stat().st_size, audio_mtime_ns=audio.stat().st_mtime_ns,
            bt=bt.tolist(), fase=fase, bpm=float(bpm), notas=[], diagnostico={}, acordes=acs, palavras=[],
            idioma=args.idioma, leve=True, batidas="madmom" if madmom else "librosa", fonte_acordes=args.acordes,
            compasso=int(madmom[3]) if madmom else 4), ensure_ascii=False, default=lambda v: v.item()), encoding="utf-8")
    else:
        if karaoke:  # voz já separada pelo karaokê; Demucs só no acompanhamento (baixo/bateria/resto)
            stems = separar(karaoke["acompanhamento"], AQUI / "trabalho", args.separador)
            voz_wav = karaoke["voz"]
        else:
            stems = separar(audio, AQUI / "trabalho", args.separador)
            voz_wav = stems / "vocals.wav"
        sr = 22050
        mix = carregar(audio, sr)
        voz = carregar(voz_wav, sr)
        baixo = carregar(stems / "bass.wav", sr)
        resto = carregar(stems / "other.wav", sr)
        bateria = carregar(stems / "drums.wav", sr)

        print("[batidas] detectando pulso...")
        perc = bateria + 0.5 * baixo + 0.3 * resto
        bt, bpm = batidas(mix, sr, perc)
        fase = fase_compasso(bt, baixo, sr)
        grade = Grade(bt, fase)
        print(f"[batidas] ~{bpm:.0f} bpm, {len(bt)} batidas, tempo 1 na batida {fase}")

        print("[melodia] extraindo altura da voz...")
        voz16 = librosa.resample(voz, orig_sr=sr, target_sr=16000)
        ons = librosa.onset.onset_detect(y=voz, sr=sr, units="time", backtrack=True, delta=0.25)
        diagnostico = {}
        notas = melodia(voz16, 16000, ons, diagnostico=diagnostico)
        print(f"[melodia] {len(notas)} notas detectadas")

        print("[acordes] detectando harmonia...")
        harm, fonte_harm = harmonia_das_faixas(stems, sr)
        n_ = min(len(harm), len(baixo))
        print(f"[acordes] harmonia de: {fonte_harm}")
        acs = acordes(harm[:n_] + 0.3 * baixo[:n_], baixo, sr, grade)
        fase, acs, mudou = corrigir_fase(fase, acs)
        if mudou:
            grade = Grade(bt, fase)
            print(f"[batidas] tempo 1 corrigido pela harmonia: batida {fase}")

        palavras = []
        origem_letra, rel_alinhamento = None, None
        if not args.sem_letra and karaoke and karaoke["palavras"]:
            palavras, origem_letra = karaoke["palavras"], "karaoke"
            print(f"[letra] {len(palavras)} palavras do karaokê (segments.json)")
        elif not args.sem_letra:
            from letra import palavras_com_tempo
            oficial = args.letra.read_text(encoding="utf-8") if args.letra else None
            sincronizada = None
            if karaoke and oficial is None:
                oficial, sincronizada = karaoke["plain_lyrics"], karaoke["synced_lyrics"]
            if oficial is None and not args.sem_busca_letra:
                from letra import buscar_letra
                artista = args.artista or re.split(r"\s[—–/·]\s|\s-\s", args.subtitulo)[0]
                oficial, sincronizada = buscar_letra(titulo, artista, com_sincronizada=True)
            palavras = palavras_com_tempo(voz_wav, args.idioma, oficial)
            origem_letra = "whisper"
            if args.idioma == "auto":
                import letra
                args.idioma = letra.IDIOMA_DETECTADO
            if oficial and not args.sem_alinhamento:
                from alinhamento import palavras_alinhadas
                alinhadas, rel_alinhamento = palavras_alinhadas(voz_wav, oficial, args.idioma, whisper=palavras,
                                                                sincronizada=sincronizada)
                if alinhadas:
                    palavras, origem_letra = alinhadas, "alinhamento"

        cache=base/'cache'
        cache.mkdir(parents=True,exist_ok=True)
        transcricao=dict(audio=str(audio),audio_tamanho=audio.stat().st_size,
            audio_mtime_ns=audio.stat().st_mtime_ns,bt=bt.tolist(),fase=fase,bpm=float(bpm),
            notas=notas,diagnostico=diagnostico,acordes=acs,palavras=palavras,idioma=args.idioma,
            origem_letra=origem_letra,alinhamento=rel_alinhamento,separador=args.separador)
        (cache/'transcricao.json').write_text(json.dumps(transcricao,ensure_ascii=False,
            default=lambda v:v.item()),encoding='utf-8')
    if not getattr(args, "melodia_crua", False) and notas:  # afinação + notas duvidosas da voz puxadas pra escala
        from afinacao import melodia_no_tom
        notas, reg_tom, cents = melodia_no_tom(notas, (diagnostico or {}).get("quadros"), acs, TIPOS, grade.pos)
        print(f"[afinacao] voz {cents:+d} cents; {sum(r['motivo'] == 'tom' for r in reg_tom)} notas fora do tom "
              f"puxadas pra escala, {sum(r['motivo'] == 'afinacao' for r in reg_tom)} pela afinação")
        (base / "cache").mkdir(parents=True, exist_ok=True)
        (base / "cache" / "melodia_no_tom.json").write_text(
            json.dumps(dict(cents=cents, mudancas=reg_tom), ensure_ascii=False), encoding="utf-8")
    PREVIAS_PENDENTES = []   # prévias de todos os níveis renderizadas juntas no fim, em paralelo
    for nivel in niveis:
        SR_GRADE = GRADE_NIVEL["medio" if ((nivel == "facil" and args.facil_fiel) or args.derivar) else nivel]
        if getattr(args, "leve", False):
            gerar_nivel_leve(nivel, args, audio, base, titulo, acs, grade, bpm)
        else:
            gerar_nivel(nivel, args, audio, base, titulo, notas, acs, palavras, grade, bpm, diagnostico)
    renderizar_previas_pendentes()


def gerar_nivel(nivel, args, audio, base, titulo, notas, acs, palavras, grade, bpm, diagnostico=None):
    """Gera as versões pedidas (Acordes sempre; Híbrido/Pop2Piano se pedidos) num nível."""
    nivel_alvo = nivel
    if getattr(args, "derivar", False) and nivel != "medio":
        nivel = "medio"   # monta tudo como no médio; fácil/difícil saem dele no fim (derivados.py)
    from niveis import (NOME, cifras_do_nivel, mao_esquerda_acordes, reduzir_mao,
                        transpor_facil, completar_instrumentais, suavizar_baixo,
                        fechar_acordes, simplificar_passagens)
    print(f"\n=== nível {NOME[nivel]} (grade 1/{SR_GRADE} de tempo) ===")
    from protecao_melodia import proteger_melodia
    usadas,correcoes=proteger_melodia(notas,grade,nivel,palavras,diagnostico)
    print(f"[protecao] {NOME[nivel]}: {len(correcoes)} transições/ataques instáveis filtrados")
    if diagnostico is not None:
        cache=base/'cache'; cache.mkdir(parents=True,exist_ok=True)
        (cache/f'protecao_{nivel}.json').write_text(json.dumps(correcoes,ensure_ascii=False),encoding='utf-8')
    if palavras:  # palavra cantada que o detector não pegou (ex.: começo de verso) ganha nota
        from palavras_sem_nota import notas_para_palavras
        usadas, log_palavras = notas_para_palavras(usadas, palavras, (diagnostico or {}).get('quadros'))
        criadas = [x for x in log_palavras if x['criada']]
        print(f"[palavras] {len(criadas)} notas criadas pra palavras sem nota, "
              f"{len(log_palavras)-len(criadas)} recusadas")
        if diagnostico is not None:
            (base/'cache'/f'palavras_sem_nota_{nivel}.json').write_text(
                json.dumps(log_palavras, ensure_ascii=False), encoding='utf-8')
    fiel = nivel == 'facil' and getattr(args, 'facil_fiel', False)
    usadas = simplificar_passagens(usadas,palavras) if (nivel=='facil' and not fiel) else usadas
    if nivel == 'facil' and not fiel:  # menos acidentes: cromatismo curto que não é do acorde vai pra escala
        from niveis import alinhar_cromaticas, escala_da_armadura
        cromaticas = [(b_-a_, [p]) for a_,b_,p in usadas] + [
            (.3*2, [(r+i) % 12 + 48 for i in TIPOS[t][0]]) for _,r,t,*_ in acs if r is not None]
        escala = escala_da_armadura(escolher_armadura(cromaticas))
        usadas, mudadas = alinhar_cromaticas(usadas, palavras, grade.pos, acs, TIPOS, escala)
        print(f"[facil] {len(mudadas)} notas cromáticas curtas levadas pra escala")
        if diagnostico is not None:
            (base/'cache'/'cromaticas_facil.json').write_text(json.dumps(mudadas), encoding='utf-8')
    notas_q = quantizar_melodia(usadas, grade)
    letras = {}
    if palavras:
        from letra import letra_nas_notas
        letras = letra_nas_notas(notas_q, palavras, args.idioma)
    print(f"[melodia] {len(notas_q)} notas quantizadas, {len(letras)} com sílaba")
    # voz sustentada a um semitom do acorde detectado: corrige a qualidade (C7 x C7M etc.)
    from harmonia import corrigir_qualidade, tirar_choques
    acs, mud_qualidade = corrigir_qualidade(acs, notas_q, TIPOS)
    print(f"[harmonia] {len(mud_qualidade)} acordes com a qualidade corrigida pela melodia")
    if not getattr(args, "repetidas", False):  # repetida colada sem sílaba vira nota sustentada
        from limpeza import tirar_bordaduras
        notas_q, bordaduras = tirar_bordaduras(notas_q, letras)   # A-B-A tremido: B vira A
        notas_q, letras, juntadas = juntar_repetidas(notas_q, letras, getattr(args, "juntar_silabas", False))
        print(f"[melodia] {bordaduras} bordaduras falsas tiradas, {juntadas} notas repetidas juntadas numa nota sustentada")
    md_ev, _, cifras = eventos_melodia_acordes(notas_q, acs, letras=letras)
    fim = max(n[1] for n in notas_q) + 4
    cifras = cifras_do_nivel(cifras, nivel)

    bloqueios = [(grade.pos(a)-.5, grade.pos(b)+.5) for a,b,_ in palavras]
    versoes = {"Acordes": (md_ev, suavizar_baixo(fechar_acordes(mao_esquerda_acordes(acs, nivel, fim, TIPOS)), nivel))}
    teor_acomp = getattr(args, "acompanhamento", None)
    pedais_acomp = []
    if teor_acomp:  # esquerda da música inteira no teor escolhido (só na versão Acordes)
        from acompanhamento import acompanhamento_no_teor
        me_teor, pedais_acomp, info_acomp = acompanhamento_no_teor(
            acs, md_ev, TIPOS, nivel, teor_acomp, fim, getattr(args, "variacao", 0))
        versoes["Acordes"] = (md_ev, me_teor)
        print(f"[acompanhamento] {teor_acomp}: {len(me_teor)} eventos, "
              f"{info_acomp['compassos_simplificados_pelo_canto']} compassos simplificados pelo canto")
    if args.hibrido or args.pop2piano:
        from pop2piano import maos_pop2piano
        p2p_md, p2p_me = maos_pop2piano(audio, base, grade, f"composer{args.estilo}")
        if args.hibrido:
            dir_ia = reduzir_mao(p2p_md, nivel, "direita")
            completa = completar_instrumentais(md_ev, dir_ia, grade.passo, bloqueios)
            print(f"[instrumental] Hibrido: {len(completa)-len(md_ev)} ataques acrescentados")
            versoes["Hibrido"] = (completa, reduzir_mao(p2p_me, nivel, "esquerda"))
        if args.pop2piano:
            versoes["Pop2Piano"] = (reduzir_mao(p2p_md, nivel, "direita"), reduzir_mao(p2p_me, nivel, "esquerda"))
    if args.amtapc:  # os "levels" do AMT-APC são mais estilo que dificuldade: simplifica igual ao Pop2Piano
        from amtapc import maos_amtapc
        a_md, a_me = maos_amtapc(audio, base, nivel, grade)
        r_md, r_me = reduzir_mao(a_md, nivel, "direita"), reduzir_mao(a_me, nivel, "esquerda")
        if not getattr(args, "tom_ia_cru", False):   # nota fora do tom do arranjo da IA (tonalidade.py)
            from tonalidade import corrigir_tom
            r_md, r_me, reg_tom = corrigir_tom(r_md, r_me, acs, TIPOS)
            print(f"[tonalidade] AMT-APC: {len(reg_tom)} notas fora do tom corrigidas")
        versoes["AMT-APC"] = (r_md, r_me)
        a_me_corrigida = r_me
        if args.hibrido:  # melodia cantada com letra + mão esquerda do AMT-APC (mais tocável que a do Pop2Piano)
            dir_ia = r_md
            completa = completar_instrumentais(md_ev, dir_ia, grade.passo, bloqueios)
            print(f"[instrumental] HibridoAMT: {len(completa)-len(md_ev)} ataques acrescentados")
            versoes["HibridoAMT"] = (completa, a_me_corrigida)
    if getattr(args, "gravado", False):  # piano + violão tocados na gravação, transcritos nota a nota
        from gravado import completar_com, maos_gravado
        g_md, g_me = maos_gravado(audio, base, grade)
        completa = completar_instrumentais(md_ev, reduzir_mao(g_md, nivel, "direita"), grade.passo, bloqueios)
        esq, preenchidos = completar_com(reduzir_mao(g_me, nivel, "esquerda"), versoes["Acordes"][1])
        print(f"[gravado] {len(completa)-len(md_ev)} ataques instrumentais na direita; "
              f"{preenchidos} compassos sem piano/violão completados com a esquerda da versão Acordes")
        versoes["HibridoGravado"] = (completa, esq)
    marcas_derivadas = {}
    if nivel_alvo != nivel:
        from derivados import dificil_de_medio, facil_de_medio
        for v, (md_v, me_v) in list(versoes.items()):
            if nivel_alvo == "facil":
                md_v, me_v, mv = facil_de_medio(md_v, me_v, acs, TIPOS)
            else:
                md_v, me_v, mv = dificil_de_medio(md_v, me_v, acs, TIPOS, bpm)
            versoes[v], marcas_derivadas[v] = (md_v, me_v), mv
        print(f"[derivar] {NOME[nivel_alvo]} derivado do médio em {len(versoes)} versões")
        nivel = nivel_alvo
        cifras = cifras_do_nivel(cifras, nivel)

    k = 0
    if nivel == "facil" and not args.sem_transpor and not getattr(args, "derivar", False) and not getattr(args, "facil_fiel", False):  # mesmo intervalo pra todas as versões
        _, _, _, k = transpor_facil(*versoes["Acordes"], cifras)
    sub = args.subtitulo + f" · nível {NOME[nivel].lower().replace('facil', 'fácil').replace('dificil', 'difícil')}"
    if k:
        sub += f" (transposto {k:+d} semitons)"
        print(f"[nível] transposto {k:+d} semitons pra tom sem acidentes")
    intro = None
    teor = getattr(args, "introducao", None)
    if teor:  # introdução gerada (não existe na gravação), a mesma pra todas as versões do nível
        from introducao import gerar_introducao, NOME_TEOR
        inicio_canto = min(e[0] for e in md_ev)
        intro = gerar_introducao(md_ev, acs, TIPOS, nivel, teor, inicio_musica=inicio_canto,
                                 semente=titulo, variacao=getattr(args, "variacao", 0))
        info = intro[3]
        print(f"[introducao] {NOME_TEOR[teor]}, {info['compassos']} compassos, motivo de {info['refrao']}")
        (base / "cache").mkdir(parents=True, exist_ok=True)
        (base / "cache" / f"introducao_{nivel}.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        sub += f" · introdução gerada ({NOME_TEOR[teor]})"
    final = None
    teor_final = getattr(args, "final", None)
    if teor_final:  # final gerado (não existe na gravação)
        from introducao import gerar_final, NOME_TEOR
        final = gerar_final(md_ev, acs, TIPOS, nivel, teor_final, inicio_musica=min(e[0] for e in md_ev),
                            variacao=getattr(args, "variacao", 0))
        print(f"[final] {NOME_TEOR[teor_final]}, {final[3]['compassos']} compassos")
        (base / "cache").mkdir(parents=True, exist_ok=True)
        (base / "cache" / f"final_{nivel}.json").write_text(json.dumps(final[3], ensure_ascii=False), encoding="utf-8")
        sub += f" · final gerado ({NOME_TEOR[teor_final]})"
    so = {v.strip() for v in getattr(args, "versoes", "").split(",") if v.strip()}
    for versao, (md, me) in versoes.items():
        if so and versao not in so:
            continue
        cf = cifras
        if k:
            md = [(o, d, [p + k for p in ps], *r) for o, d, ps, *r in md]
            me = [(o, d, [p + k for p in ps], *r) for o, d, ps, *r in me]
            cf = [(o, (r + k) % 12, t) for o, r, t in cifras]
        marcas = []
        if intro:
            md, me, cf, marcas = com_introducao(md, me, cf, intro, k)
        if final:
            md, me, cf, marcas_f = com_final(md, me, cf, final, k)
            marcas += marcas_f
        marcas += marcas_derivadas.get(versao, [])   # pedal/fermata do difícil derivado
        if not getattr(args, "repetidas", False):
            from limpeza import juntar_repetidas_esquerda, melodia_no_topo
            me = juntar_repetidas_esquerda(me)            # Si♭ Si♭ Si♭ colado na esquerda: nota segurada
            md, me, no_topo = melodia_no_topo(md, me)     # nada do acompanhamento acima da nota cantada
            print(f"[melodia] {versao}: {no_topo} notas do acompanhamento acima da melodia tiradas")
        if teor_acomp and versao == "Acordes":
            from introducao import DINAMICA
            inicio_mus = 4.0 * np.floor(min(e[0] for e in md_ev) / 4)
            # a dinâmica da música passa a ser a do teor (no lugar do mf da introdução)
            marcas = [m_ for m_ in marcas if not (m_[1] == "dinamica" and abs(m_[0] - inicio_mus) < 1e-6)]
            marcas += [(inicio_mus, "dinamica", DINAMICA[teor_acomp])]
            marcas += [(a, "pedal", b) for a, b in pedais_acomp]
        # acompanhamento a um semitom da nota cantada forte: tira essa voz (o baixo fica)
        melodia_k = [(o, d, [p + k for p in ps]) for o, d, ps, *_ in md_ev]
        me, mud_choques = tirar_choques(melodia_k, me)
        print(f"[harmonia] {versao}: {len(mud_choques)} vozes do acompanhamento tiradas por choque com a melodia")
        if diagnostico is not None:
            (base / "cache" / f"harmonia_{versao}_{nivel}.json").write_text(
                json.dumps(dict(qualidade=mud_qualidade, choques=mud_choques), ensure_ascii=False), encoding="utf-8")
        dmd = dme = None
        sem_maos, modo_dedos = getattr(args, "sem_maos", False), getattr(args, "dedos", "auto")
        if not sem_maos or modo_dedos != "nenhum":
            from maos import tornar_tocavel
            prot = {(round(o, 6), p + k) for o, _, ps, *_ in md_ev for p in ps}
            md, me, dmd, dme, rel = tornar_tocavel(
                md, me, nivel, bpm, prot, corrigir=not sem_maos,
                mostrar=None if modo_dedos == "auto" else modo_dedos,
                clarear=not getattr(args, "grave_embolado", False))
            r = rel["resumo"]
            print(f"[maos] {versao}: {r['corrigidos']} correções, {r['restantes']} trechos difíceis restantes "
                  f"({r['restantes_na_melodia']} na melodia)")
            cache = base / "cache"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / f"maos_{versao}_{nivel}.json").write_text(json.dumps(rel, ensure_ascii=False, default=_json_numpy), encoding="utf-8")
            if modo_dedos == "nenhum":
                dmd = dme = None
        sc, arm = montar_partitura(md, me, cf, bpm, titulo, sub, uma_armadura=(nivel == "facil"),
                                   dedos_md=dmd, dedos_me=dme, marcas=marcas)
        print(f"[{versao}] armadura: {arm}")
        salvar_versao(sc, base, f"{versao} - {NOME[nivel]}")
        registrar_sincronia(base, f"{versao} - {NOME[nivel]}", grade, deslocamento(md, me))

_BASE_LEVE = {}   # médio do modo leve já calculado nesta execução (serve aos três níveis)


def gerar_nivel_leve(nivel, args, audio, base, titulo, acs, grade, bpm):
    """Modo leve: só o AMT-APC (fácil e difícil derivados do médio), sem melodia nem letra."""
    from amtapc import maos_amtapc
    from derivados import dificil_de_medio, facil_de_medio
    from limpeza import juntar_repetidas_esquerda
    from maos import tornar_tocavel
    from niveis import NOME, cifras_do_nivel, reduzir_mao
    base_nivel = "medio" if getattr(args, "derivar", True) else nivel
    print(f"\n=== nível {NOME[nivel]} (modo leve, AMT-APC) ===")
    # a base (médio) é a mesma pros três níveis: calculada uma vez por música (repetições e tom são caros)
    chave = (str(audio), str(base), base_nivel, SR_GRADE, len(acs), getattr(args, "tom_ia_cru", False),
             getattr(args, "sem_repeticoes", False))
    if chave in _BASE_LEVE:
        import copy
        md, me = copy.deepcopy(_BASE_LEVE[chave])
    else:
        a_md, a_me = maos_amtapc(audio, base, base_nivel, grade)
        md, me = reduzir_mao(a_md, base_nivel, "direita"), reduzir_mao(a_me, base_nivel, "esquerda")
        if not getattr(args, "tom_ia_cru", False):   # nota fora do tom do arranjo da IA (tonalidade.py)
            from tonalidade import corrigir_tom
            md, me, reg_tom = corrigir_tom(md, me, acs, TIPOS)
            print(f"[tonalidade] AMT-APC: {len(reg_tom)} notas fora do tom corrigidas")
        if not getattr(args, "sem_repeticoes", False):   # trecho que repete escrito igual (repeticoes.py)
            from repeticoes import padronizar
            md, me, reg_rep = padronizar(md, me, audio, grade.bt, bpm=bpm)
            print(f"[repeticoes] distâncias {reg_rep['lags_compasso'][:6]} compassos; "
                  f"{reg_rep['grupos']} grupos, {reg_rep['compassos']} compassos com o mesmo padrão")
        _BASE_LEVE.clear()
        import copy
        _BASE_LEVE[chave] = copy.deepcopy((md, me))
    cifras, anterior = [], None
    for j, r, t, *_ in acs:
        if r is not None and (r, t) != anterior:
            cifras.append((j, r, t))
        anterior = (r, t) if r is not None else None
    marcas = []
    if base_nivel != nivel:
        md, me, marcas = (facil_de_medio(md, me, acs, TIPOS) if nivel == "facil"
                          else dificil_de_medio(md, me, acs, TIPOS, bpm))
    cifras = cifras_do_nivel(cifras, nivel)
    if getattr(args, "dinamica", False) and (md or me):   # p/mp/mf/f pela intensidade da gravação
        arq = base / "cache" / "dinamica.json"
        if arq.exists():
            dyn = [tuple(x) for x in json.loads(arq.read_text(encoding="utf-8"))]
        else:
            from dinamica import marcas_de_dinamica
            dyn = marcas_de_dinamica(audio, grade.bt, grade.idx, inicio=min(e[0] for e in md + me))
            arq.write_text(json.dumps(dyn), encoding="utf-8")
        marcas = list(marcas) + dyn
        print(f"[dinamica] {' '.join(f'c{int(o // 4) + 1}:{v}' for o, _, v in dyn)}")
    if not getattr(args, "sem_ajuste", False):   # tocabilidade por regra (tocavel.py)
        from tocavel import ajustar
        md, me, reg_toc = ajustar(md, me, nivel, bpm)
        print(f"[tocavel] {', '.join(f'{k} {v}' for k, v in reg_toc.items())}")
    me = juntar_repetidas_esquerda(me)
    md, me, dmd, dme, rel = tornar_tocavel(md, me, nivel, bpm, frozenset(),
                                           clarear=not getattr(args, "grave_embolado", False))
    r = rel["resumo"]
    print(f"[maos] AMT-APC: {r['corrigidos']} correções, {r['restantes']} trechos difíceis restantes")
    sub = args.subtitulo + f" · nível {NOME[nivel].lower().replace('facil', 'fácil').replace('dificil', 'difícil')}"
    sc, arm = montar_partitura(md, me, cifras, bpm, titulo, sub, uma_armadura=(nivel == "facil"),
                               dedos_md=dmd, dedos_me=dme, marcas=marcas)
    print(f"[AMT-APC] armadura: {arm}")
    salvar_versao(sc, base, f"AMT-APC - {NOME[nivel]}")
    registrar_sincronia(base, f"AMT-APC - {NOME[nivel]}", grade, deslocamento(md, me))


if __name__ == "__main__":
    main()
