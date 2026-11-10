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


def separar(audio: Path, trabalho: Path) -> Path:
    destino = trabalho / "htdemucs" / audio.stem
    if (destino / "vocals.wav").exists():
        print(f"[demucs] já separado: {destino}")
        return destino
    print("[demucs] separando faixas...")
    subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs", "-d", "cuda",
                    "-o", str(trabalho), str(audio)], check=True)
    return destino


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


def fase_compasso(bt: np.ndarray, baixo: np.ndarray, sr: int) -> int:
    """Escolhe qual batida (0..3) é o tempo 1: onde o baixo bate mais forte."""
    import librosa
    env = librosa.onset.onset_strength(y=baixo, sr=sr)
    t_env = librosa.times_like(env, sr=sr)
    forca = np.interp(bt, t_env, env)
    somas = [forca[f::4].mean() + 0.5 * forca[(f + 2) % 4::4].mean() for f in range(4)]
    return int(np.argmax(somas))


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


def acordes(harm: np.ndarray, baixo: np.ndarray, sr: int, grade: Grade, beats_por_janela=2):
    """Lista (pos_tempo, root_pc, tipo, baixo_pc) a cada `beats_por_janela` tempos."""
    import librosa
    hop = 512
    ch = librosa.feature.chroma_cqt(y=harm, sr=sr, hop_length=hop)
    chb = librosa.feature.chroma_cqt(y=baixo, sr=sr, hop_length=hop, fmin=librosa.note_to_hz("E1"), n_octaves=3)
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
    """Para cada armadura (-6..5), peso das notas que ficariam com acidente. eventos: (dur, [midis])."""
    peso = np.zeros(12)
    for d, ps in eventos:
        for p in ps:
            peso[p % 12] += d
    custo = np.zeros(12)
    for i, s in enumerate(range(-6, 6)):
        t = (7 * s) % 12
        escala = {(t + k) % 12 for k in (0, 2, 4, 5, 7, 9, 11)}
        custo[i] = sum(peso[pc] for pc in range(12) if pc not in escala) + 0.002 * abs(s) * peso.sum()
    return custo


def armaduras_por_trecho(eventos_off, fim: float, bloco: int = 32) -> list[tuple[float, int]]:
    """Mudanças de armadura [(offset, sustenidos)], em blocos de 8 compassos, com custo para trocar.
    eventos_off: (offset, dur, [midis]) já deslocados (offset >= 0)."""
    nb = max(1, int(np.ceil(fim / bloco)))
    custos = np.zeros((nb, 12))
    peso = np.zeros(nb)
    for b in range(nb):
        ev = [(d, ps) for o, d, ps in eventos_off if b * bloco <= o < (b + 1) * bloco]
        custos[b] = _custo_armaduras(ev)
        peso[b] = sum(d * len(ps) for d, ps in ev)
    # Exigir evidência mais forte de modulação: acordes cromáticos isolados não
    # justificam trocar a armadura de leitura a cada bloco de oito compassos.
    troca = 0.25 * float(np.median(peso[peso > 0])) if (peso > 0).any() else 0.0
    dp = custos[0].copy()
    back = np.zeros((nb, 12), dtype=int)
    for b in range(1, nb):
        melhor = int(dp.argmin())
        fica, muda = dp, dp[melhor] + troca
        back[b] = np.where(fica <= muda, np.arange(12), melhor)
        dp = np.minimum(fica, muda) + custos[b]
    k = int(dp.argmin())
    seq = [k]
    for b in range(nb - 1, 0, -1):
        k = back[b, k]
        seq.append(k)
    seq = seq[::-1]
    mudancas = []
    for b, k in enumerate(seq):
        if not mudancas or mudancas[-1][1] != k - 6:
            mudancas.append((float(b * bloco), k - 6))
    return mudancas


def escolher_armadura(eventos) -> int:
    return int(np.argmin(_custo_armaduras(eventos))) - 6


def nomes_para(sustenidos: int) -> list[str]:
    if sustenidos < 0:
        return NOMES_PC_BEMOL
    return NOMES_PC_SUST if sustenidos >= 3 else NOMES_PC


def montar_partitura(md_ev, me_ev, cifras, bpm: float, titulo: str, subtitulo: str, uma_armadura=False):
    """md_ev / me_ev: (offset_em_tempos, duração, [midis]) sem sobreposição dentro da mão.
    cifras: (offset, root_pc, tipo)."""
    from music21 import (chord, clef, harmony, key, layout, meter, metadata, note, pitch, stream,
                         tempo)

    tudo = md_ev + me_ev
    if not tudo:
        sys.exit("nenhuma nota detectada")
    desloc = -np.floor(min(e[0] for e in tudo) / 4) * 4  # começa num compasso inteiro
    fim = max(e[0] + e[1] for e in tudo) + desloc
    # melodia manda; acordes da mão esquerda entram com peso menor (cada um soma 3 notas)
    if uma_armadura:  # nível fácil: armadura única, sem mudanças no meio
        mudancas = [(0.0, escolher_armadura([(e[1], e[2]) for e in md_ev] + [(0.3 * e[1], e[2]) for e in me_ev]))]
    else:
        mudancas = armaduras_por_trecho([(e[0] + desloc, e[1], e[2]) for e in md_ev]
                                        + [(e[0] + desloc, 0.3 * e[1], e[2]) for e in me_ev], fim)

    def sust_em(off):
        s_ = mudancas[0][1]
        for o, k_ in mudancas:
            if off >= o:
                s_ = k_
        return s_

    def nome_raiz(r, off):
        sus = sust_em(off)
        if sus < 0:
            return ["C", "D-", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B"][r]
        return (NOMES_PC_SUST if sus >= 3 else NOMES_PC)[r]

    # grafia das notas do acorde vem da cifra (A7 = A C# E G, nunca D-)
    ativos = []
    for off, r, tipo in cifras:
        cs = harmony.ChordSymbol(root=nome_raiz(r, off + desloc), kind=TIPOS[tipo][1])
        ativos.append((off + desloc, {q.pitchClass: q.name for q in cs.pitches}))

    def P(m, off):
        nomes_pc = {}
        for o, mapa in ativos:
            if o <= off + 1e-6:
                nomes_pc = mapa
            else:
                break
        nome = nomes_pc.get(m % 12) or nomes_para(sust_em(off))[m % 12]
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

    for parte, eventos in ((md, md_ev), (me, me_ev)):
        for off, dur, ps, *resto in eventos:
            o = off + desloc
            el = note.Note(P(ps[0], o)) if len(ps) == 1 else chord.Chord([P(m, o) for m in sorted(ps)])
            el.quarterLength = dur
            if resto and resto[0]:
                el.addLyric(resto[0])  # "tris-" / "-te-" / "-za" viram sílabas ligadas
            parte.insert(o, el)

    simbolos = []
    for off, r, tipo in cifras:
        o = off + desloc
        if o < 0:
            continue
        cs = harmony.ChordSymbol(root=nome_raiz(r, o), kind=TIPOS[tipo][1])
        cs.writeAsChord = False
        simbolos.append((o, cs))
        md.insert(o, cs)

    sc = stream.Score()
    sc.metadata = metadata.Metadata()
    sc.metadata.title = titulo
    sc.metadata.composer = subtitulo
    sc.insert(0, md)
    sc.insert(0, me)
    sc.insert(0, layout.StaffGroup([md, me], symbol="brace", barTogether=True, name="Piano"))
    for p in (md, me):
        p.makeRests(fillGaps=True, inPlace=True, timeRangeFromBarDuration=True)
    sc = sc.makeNotation()
    # makeNotation põe bequadro nas cifras ("A♮m7"); cifra não leva acidente de armadura
    for cs in sc.recurse().getElementsByClass(harmony.ChordSymbol):
        for p_ in list(cs.pitches) + [cs.root(), cs.bass()]:
            if p_ is not None and p_.accidental is not None and p_.accidental.name == "natural":
                p_.accidental = None
    return sc, ", ".join(f"compasso {int(o // 4) + 1}: {k_:+d}" for o, k_ in mudancas)


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


def salvar_versao(sc, pasta: Path, versao: str, mid_previa: Path | None = None):
    """pasta/Versao.pdf + pasta/Versao - previa.mp3 + pasta/editaveis/Versao.musicxml|.mid"""
    ed = pasta / "editaveis"
    ed.mkdir(parents=True, exist_ok=True)
    xml, mid, pdf = ed / f"{versao}.musicxml", ed / f"{versao}.mid", pasta / f"{versao}.pdf"
    sc.write("musicxml", fp=str(xml))
    salvar_midi_notas(sc, mid, xml)
    n = xml_para_pdf(xml, pdf)
    midi_para_mp3(mid_previa or mid, pasta / f"{versao} - previa.mp3")
    print(f"[ok] {pdf} ({n} páginas)")


def salvar_midi_notas(sc, destino: Path, xml: Path | None = None):
    """Exporta somente notas escritas e respeita ligações parciais de acordes."""
    import pretty_midi
    from music21 import musicxml
    from sincronia import preparar_musicxml, notas_ligadas
    import xml.etree.ElementTree as ET
    texto=xml.read_text(encoding='utf-8') if xml else musicxml.m21ToXml.GeneralObjectExporter(sc).parse().decode('utf-8')
    _,segmentos=preparar_musicxml(texto)
    som=ET.fromstring(texto).find('.//sound[@tempo]')
    bpm=float(som.get('tempo')) if som is not None else 120
    pm=pretty_midi.PrettyMIDI(initial_tempo=bpm)
    instrumentos={}
    for n in notas_ligadas(segmentos):
        inst=instrumentos.setdefault(n['voz'],pretty_midi.Instrument(program=0,name=n['voz']))
        inst.notes.append(pretty_midi.Note(velocity=90,pitch=n['pitch'],start=n['inicio'],end=n['fim']))
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


def xml_para_verovio(texto: str) -> str:
    """Verovio não aceita layer zero; renumerar sem alterar conteúdo musical."""
    if '<voice>0</voice>' not in texto:
        return texto
    import xml.etree.ElementTree as ET
    raiz=ET.fromstring(texto)
    for voz in raiz.iter('voice'):
        if voz.text and voz.text.isdigit():
            voz.text=str(int(voz.text)+1)
    return ET.tostring(raiz,encoding='unicode')


def xml_para_pdf(xml: Path, pdf: Path):
    import verovio
    verovio.enableLog(False)
    tk = verovio.toolkit()
    tk.setResourcePath(str(Path(verovio.__file__).parent / 'data'))
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 42,
                   "pageMarginTop": 80, "pageMarginBottom": 80,
                   "pageMarginLeft": 80, "pageMarginRight": 80,
                   "adjustPageHeight": False, "footer": "none", "breaks": "auto"})
    if not tk.loadData(xml_para_verovio(xml.read_text(encoding="utf-8"))):  # loadFile falha com acento no caminho (Windows)
        raise RuntimeError(f"Verovio não conseguiu ler o MusicXML: {xml}")
    pags = [_desembaralhar(tk.renderToSVG(i)) for i in range(1, tk.getPageCount() + 1)]
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
    tmp_mid = mp3.with_name("_tmp_previa.mid")
    wav = mp3.with_name("_tmp_previa.wav")
    pm.write(str(tmp_mid))
    subprocess.run([fs, "-ni", "-q", "-g", "0.8", "-r", "44100",
                    "-o", "synth.reverb.active=1", "-o", "synth.reverb.room-size=0.6",
                    "-o", "synth.reverb.level=0.35",
                    "-F", str(wav), str(sf2), str(tmp_mid)], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav),
                    "-af", "loudnorm=I=-16:TP=-1.5", "-b:a", "192k", str(mp3)], check=True)
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
    ap.add_argument("audio", type=Path)
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
    ap.add_argument("--sem-transpor", action="store_true", help="no nível fácil, não transpõe pra tom sem acidentes")
    args = ap.parse_args()
    global SR_GRADE
    from niveis import NIVEIS
    niveis = list(NIVEIS) if args.nivel == "todos" else [n.strip() for n in args.nivel.split(",")]
    for n in niveis:
        if n not in NIVEIS:
            ap.error(f"nível inválido: {n} (use {', '.join(NIVEIS)})")

    import librosa
    audio = args.audio.resolve()
    titulo = args.titulo or audio.stem.replace("_", " ").title()
    args.saida.mkdir(parents=True, exist_ok=True)
    base = args.saida / (args.pasta or nome_pasta(titulo))  # uma pasta por música
    copiar_original(audio, base)

    stems = separar(audio, AQUI / "trabalho")
    sr = 22050
    mix = carregar(audio, sr)
    voz = carregar(stems / "vocals.wav", sr)
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
    acs = acordes(resto + 0.3 * baixo, baixo, sr, grade)

    palavras = []
    if not args.sem_letra:
        from letra import palavras_com_tempo
        oficial = args.letra.read_text(encoding="utf-8") if args.letra else None
        if oficial is None and not args.sem_busca_letra:
            from letra import buscar_letra
            artista = args.artista or re.split(r"\s[—–/·]\s|\s-\s", args.subtitulo)[0]
            oficial = buscar_letra(titulo, artista)
        palavras = palavras_com_tempo(stems / "vocals.wav", args.idioma, oficial)
        if args.idioma == "auto":
            import letra
            args.idioma = letra.IDIOMA_DETECTADO

    cache=base/'cache'
    cache.mkdir(parents=True,exist_ok=True)
    transcricao=dict(audio=str(audio),audio_tamanho=audio.stat().st_size,
        audio_mtime_ns=audio.stat().st_mtime_ns,bt=bt.tolist(),fase=fase,bpm=float(bpm),
        notas=notas,diagnostico=diagnostico,acordes=acs,palavras=palavras,idioma=args.idioma)
    (cache/'transcricao.json').write_text(json.dumps(transcricao,ensure_ascii=False,
        default=lambda v:v.item()),encoding='utf-8')
    for nivel in niveis:
        SR_GRADE = GRADE_NIVEL[nivel]
        gerar_nivel(nivel, args, audio, base, titulo, notas, acs, palavras, grade, bpm, diagnostico)


def gerar_nivel(nivel, args, audio, base, titulo, notas, acs, palavras, grade, bpm, diagnostico=None):
    """Gera as versões pedidas (Acordes sempre; Híbrido/Pop2Piano se pedidos) num nível."""
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
    usadas = simplificar_passagens(usadas,palavras) if nivel=='facil' else usadas
    notas_q = quantizar_melodia(usadas, grade)
    letras = {}
    if palavras:
        from letra import letra_nas_notas
        letras = letra_nas_notas(notas_q, palavras, args.idioma)
    print(f"[melodia] {len(notas_q)} notas quantizadas, {len(letras)} com sílaba")
    md_ev, _, cifras = eventos_melodia_acordes(notas_q, acs, letras=letras)
    fim = max(n[1] for n in notas_q) + 4
    cifras = cifras_do_nivel(cifras, nivel)

    bloqueios = [(grade.pos(a)-.5, grade.pos(b)+.5) for a,b,_ in palavras]
    versoes = {"Acordes": (md_ev, suavizar_baixo(fechar_acordes(mao_esquerda_acordes(acs, nivel, fim, TIPOS)), nivel))}
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
        versoes["AMT-APC"] = (reduzir_mao(a_md, nivel, "direita"), reduzir_mao(a_me, nivel, "esquerda"))
        if args.hibrido:  # melodia cantada com letra + mão esquerda do AMT-APC (mais tocável que a do Pop2Piano)
            dir_ia = reduzir_mao(a_md, nivel, "direita")
            completa = completar_instrumentais(md_ev, dir_ia, grade.passo, bloqueios)
            print(f"[instrumental] HibridoAMT: {len(completa)-len(md_ev)} ataques acrescentados")
            versoes["HibridoAMT"] = (completa, reduzir_mao(a_me, nivel, "esquerda"))

    k = 0
    if nivel == "facil" and not args.sem_transpor:  # mesmo intervalo pra todas as versões
        _, _, _, k = transpor_facil(*versoes["Acordes"], cifras)
    sub = args.subtitulo + f" · nível {NOME[nivel].lower().replace('facil', 'fácil').replace('dificil', 'difícil')}"
    if k:
        sub += f" (transposto {k:+d} semitons)"
        print(f"[nível] transposto {k:+d} semitons pra tom sem acidentes")
    for versao, (md, me) in versoes.items():
        cf = cifras
        if k:
            md = [(o, d, [p + k for p in ps], *r) for o, d, ps, *r in md]
            me = [(o, d, [p + k for p in ps], *r) for o, d, ps, *r in me]
            cf = [(o, (r + k) % 12, t) for o, r, t in cifras]
        sc, arm = montar_partitura(md, me, cf, bpm, titulo, sub, uma_armadura=(nivel == "facil"))
        print(f"[{versao}] armadura: {arm}")
        salvar_versao(sc, base, f"{versao} - {NOME[nivel]}")

if __name__ == "__main__":
    main()
