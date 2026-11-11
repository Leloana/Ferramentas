"""Qualidade da partitura pronta como um pianista a leria, tocaria e ouviria (sem LLM, sem ouvir ninguém).

Complementa o `regressao.py` (linhas suplementares, acidentes, trechos intocáveis, síncopes...) com:

Leitura (maior = pior):
- lig_por_100: ligaduras de prolongamento por 100 notas (figura quebrada na barra/no tempo);
- pausas_por_compasso: pausas que não são de compasso inteiro (texto picado);
- vozes_extra_pct: compassos com 2+ vozes na mesma pauta;
- curtas_pct: notas de semicolcheia ou menores; pontuadas_pct: figuras pontuadas;
- figuras_distintas: combinações figura+ponto usadas;
- acid_por_100, sup_por_100: acidentes e linhas suplementares (clave de sol) por 100 notas;
- evitaveis_por_100: notas escritas com acidente embora a altura esteja na escala da armadura
  (a enarmônica dispensaria o acidente: Mi♭ num tom de 6♯, onde Ré♯ já está na armadura);
- sup_fa_por_100: linhas suplementares na clave de fá (baixo grave demais ou alto demais).
Tocabilidade (maior = pior):
- abertura_max_d/e: maior acorde da mão (semitons); acordes_largos: acordes > 1 oitava;
- pico_ataques_s_d/e: ataques por segundo na janela de 2 s mais cheia;
- repetidas_rapidas: mesma tecla de novo em < 0,18 s na mesma mão;
- maos_cruzadas: instantes em que a esquerda soa acima (ou na mesma tecla) da direita.
Som (indicado):
- choques_por_100 (pior): 2ª menor/9ª menor soando juntas entre as mãos, por 100 ataques;
- fora_acorde_forte_pct (pior): nota de cima da direita no tempo fora do acorde detectado;
- baixo_raiz_pct, baixo_acorde_pct (melhor): baixo da esquerda na fundamental/no acorde nas trocas;
- croma_audio (melhor): semelhança (cosseno) do croma da partitura com o da gravação, por meio tempo
  (nota atacada dentro de uma região de pedal soa até o pedal soltar);
- croma_audio_ia: o mesmo pro MIDI cru do AMT-APC (teto de referência da música);
- recall_ia, precisao_ia (melhor): ataques (altura exata, ±0,15 s) do AMT-APC que ficaram / que vieram dele;
- saltos_topo_pct (pior): saltos maiores que uma oitava na voz de cima da direita (melodia).
"""
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

EPS = 1e-6
CURTAS = {"16th", "32nd", "64th", "128th"}


# ------------------------------------------------------------------ leitura (direto do MusicXML)

def leitura(texto: str) -> dict:
    raiz = ET.fromstring(texto.encode("utf-8"))
    notas = ligs = pausas = pont = curtas = compassos = vozes_extra = 0
    evitaveis = sup_fa = 0
    figuras = set()
    for parte in raiz.iter("part"):
        quintas = 0
        for m in parte.iter("measure"):
            compassos += 1
            vozes = {}
            q = m.find("attributes/key/fifths")
            if q is not None:
                quintas = int(q.text)
            na_armadura = _alteracoes(quintas)
            escala = {(7 * quintas + k) % 12 for k in (0, 2, 4, 5, 7, 9, 11)}
            for n in m.iter("note"):
                p_ = n.find("pitch")
                if p_ is not None:
                    passo, alt, oit = p_.findtext("step"), float(p_.findtext("alter") or 0), int(p_.findtext("octave"))
                    midi = 12 * (oit + 1) + _PC[passo] + int(alt)
                    # nota escrita com alteração diferente da armadura, mas cuja altura está na escala do
                    # tom: outra grafia (enarmônica) dispensaria o acidente
                    if alt != na_armadura.get(passo, 0) and midi % 12 in escala:
                        evitaveis += 1
                    if (n.findtext("staff") or "1").strip() == "2" and _clave_fa(n, m):
                        d = "CDEFGAB".index(passo) + 7 * oit + 1        # Dó4 = 29
                        sup_fa += (19 - d) // 2 if d <= 17 else ((d - 27) // 2 if d >= 29 else 0)
                staff = (n.findtext("staff") or "1").strip()
                vozes.setdefault(staff, set()).add((n.findtext("voice") or "1").strip())
                tipo = n.findtext("type") or ""
                pontos = len(n.findall("dot"))
                if n.find("rest") is not None:
                    if n.find("rest").get("measure") != "yes" and tipo not in ("whole", ""):
                        pausas += 1
                    continue
                if n.find("chord") is not None:
                    continue          # nota de acorde: a figura é a da 1ª
                notas += 1
                figuras.add((tipo, pontos))
                pont += pontos > 0
                curtas += tipo in CURTAS
                if any(t.get("type") == "start" for t in n.findall("tie")):
                    ligs += 1
            vozes_extra += any(len(v) > 1 for v in vozes.values())
    compassos = max(1, compassos // max(1, len(list(raiz.iter("part")))))
    n = max(1, notas)
    return dict(lig_por_100=round(100 * ligs / n, 2), pausas_por_compasso=round(pausas / compassos, 3),
                vozes_extra_pct=round(100 * vozes_extra / compassos, 2), curtas_pct=round(100 * curtas / n, 2),
                pontuadas_pct=round(100 * pont / n, 2), figuras_distintas=len(figuras), ataques_escritos=notas,
                evitaveis_por_100=round(100 * evitaveis / n, 2), sup_fa_por_100=round(100 * sup_fa / n, 2))


_PC = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)


def _alteracoes(quintas: int) -> dict:
    ordem = "FCGDAEB" if quintas >= 0 else "BEADGCF"
    return {s: (1 if quintas > 0 else -1) for s in ordem[:abs(quintas)]}


def _clave_fa(n, m) -> bool:
    return True    # a pauta de baixo é sempre clave de fá no gerar.montar_partitura


# ------------------------------------------------------------------ tocabilidade e som (eventos)

def _ataques(ev):
    a = {}
    for o, d, ps in ev:
        if ps:
            a.setdefault(round(o, 6), set()).update(ps)
    return sorted(a.items())


def _soando(ev, o):
    return [p for o2, d2, ps in ev for p in ps if o2 <= o + EPS and o < o2 + d2 - EPS]


def tocabilidade(md, me, bpm) -> dict:
    s_por_tempo = 60.0 / bpm
    r = {}
    for lado, ev in (("d", md), ("e", me)):
        at = _ataques(ev)
        aberturas = [max(ps) - min(ps) for _, ps in at]
        r[f"abertura_max_{lado}"] = max(aberturas or [0])
        r[f"acordes_largos_{lado}"] = sum(a > 12 for a in aberturas)
        t = np.array([o * s_por_tempo for o, _ in at])
        pico = 0.0
        if len(t):
            j = 0
            for i in range(len(t)):
                while t[i] - t[j] > 2.0:
                    j += 1
                pico = max(pico, (i - j + 1) / 2.0)
        r[f"pico_ataques_s_{lado}"] = pico
        ult, rep = {}, 0
        for o, ps in at:
            for p in ps:
                if p in ult and (o - ult[p]) * s_por_tempo < .18:
                    rep += 1
                ult[p] = o
        r[f"repetidas_rapidas_{lado}"] = rep
    cruz = 0
    for o, ps in _ataques(md + me):
        dd, ee = _soando(md, o), _soando(me, o)
        if dd and ee and max(ee) >= min(dd):
            cruz += 1
    r["maos_cruzadas"] = cruz
    return r


def _acorde_em(acs_q, q):
    """(fundamental, classes) do acorde detectado na posição q da partitura."""
    k = np.searchsorted(acs_q[0], q + EPS) - 1 if len(acs_q[0]) else -1
    if k < 0:
        return None
    return acs_q[1][k]


def som(md, me, acs, desloc, tipos) -> dict:
    # acordes: posição j da grade -> q = j + desloc na partitura
    pos, info = [], []
    for j, rr, t, *_ in acs:
        pos.append(float(j) + desloc)
        info.append(None if rr is None or t not in tipos else (rr, {(rr + i) % 12 for i in tipos[t][0]}))
    acs_q = (np.array(pos), info)
    at_total = len(_ataques(md + me)) or 1
    choques = 0
    for o, ps in _ataques(md + me):
        dd, ee = set(_soando(md, o)), set(_soando(me, o))
        novos = set(ps)
        for a in dd:
            for b in ee:
                if (a in novos or b in novos) and a > b and (a - b) % 12 == 1:
                    choques += 1
    fora = forte = 0
    for o, ps in _ataques(md):
        if abs(o - round(o)) < EPS:
            ac = _acorde_em(acs_q, o)
            if ac:
                forte += 1
                fora += max(ps) % 12 not in ac[1]
    trocas = raiz = no_acorde = 0
    ant = None
    for q, ac in zip(*acs_q):
        if ac is None or ac == ant:
            ant = ac
            continue
        ant = ac
        baixo = _soando(me, q) or _soando(md, q)
        if not baixo:
            continue
        trocas += 1
        b = min(baixo) % 12
        raiz += b == ac[0]
        no_acorde += b in ac[1]
    topo = [max(ps) for _, ps in _ataques(md)]
    saltos = sum(abs(b - a) > 12 for a, b in zip(topo, topo[1:]))
    return dict(choques_por_100=round(100 * choques / at_total, 2),
                fora_acorde_forte_pct=round(100 * fora / max(1, forte), 2),
                baixo_raiz_pct=round(100 * raiz / max(1, trocas), 2),
                baixo_acorde_pct=round(100 * no_acorde / max(1, trocas), 2),
                saltos_topo_pct=round(100 * saltos / max(1, len(topo) - 1), 2))


# ------------------------------------------------------------------ fidelidade (áudio e arranjo da IA)

def pedais(texto: str, compasso: float = 4.0):
    """Regiões de pedal [(início, fim)] em tempos, lendo os <direction><pedal> do MusicXML na ordem
    das notas (o cursor anda com <duration>, volta com <backup>, avança com <forward>)."""
    raiz = ET.fromstring(texto.encode("utf-8"))
    regioes = []
    for parte in raiz.iter("part"):
        divisoes, abertos = 1.0, {}
        for k, m in enumerate(parte.iter("measure")):
            t = 0.0
            for el in m:
                if el.tag == "attributes" and el.find("divisions") is not None:
                    divisoes = float(el.findtext("divisions"))
                elif el.tag == "note":
                    if el.find("chord") is None and el.find("grace") is None:
                        t += float(el.findtext("duration") or 0) / divisoes
                elif el.tag == "backup":
                    t -= float(el.findtext("duration") or 0) / divisoes
                elif el.tag == "forward":
                    t += float(el.findtext("duration") or 0) / divisoes
                elif el.tag == "direction":
                    for pd in el.iter("pedal"):
                        q = k * compasso + t
                        num, tipo = pd.get("number", "1"), pd.get("type")
                        if tipo == "start":
                            abertos[num] = q
                        elif tipo in ("stop", "change") and num in abertos:
                            regioes.append((abertos.pop(num), q))
                            if tipo == "change":
                                abertos[num] = q
    return sorted(regioes)


def com_pedal(ev, regioes):
    """Nota atacada dentro do pedal soa até o pedal soltar."""
    if not regioes:
        return ev
    ini = np.array([a for a, _ in regioes])
    out = []
    for o, d, ps in ev:
        k = int(np.searchsorted(ini, o + EPS)) - 1
        if k >= 0 and regioes[k][0] - EPS <= o < regioes[k][1] - EPS:
            d = max(d, regioes[k][1] - o)
        out.append((o, d, ps))
    return out


def _croma_notas(notas, celulas):
    """notas: (célula_ini, célula_fim, midi) em células de meio tempo da grade -> croma (celulas, 12)."""
    c = np.zeros((celulas, 12))
    for a, b, p in notas:
        a, b = max(0.0, a), min(float(celulas), b)
        k = int(a)
        while k < b - EPS and k < celulas:
            c[k, p % 12] += min(b, k + 1) - max(a, k)
            k += 1
    return c


def _cos(a, b):
    na, nb = np.linalg.norm(a, axis=1), np.linalg.norm(b, axis=1)
    ok = (na > EPS) & (nb > EPS)
    if not ok.any():
        return 0.0
    return float(np.mean(np.sum(a[ok] * b[ok], axis=1) / (na[ok] * nb[ok])))


def croma_audio(pasta: Path, bt, idx):
    """Croma da gravação por célula de meio tempo da grade (cache em cache/croma_audio.npy)."""
    arq = pasta / "cache" / "croma_audio.npy"
    if arq.exists():
        return np.load(arq)
    import librosa
    tr = json.loads((pasta / "cache" / "transcricao.json").read_text(encoding="utf-8"))
    y, sr = librosa.load(tr["audio"], sr=22050, mono=True)
    hop = 512
    ch = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)      # (12, quadros)
    t = librosa.frames_to_time(np.arange(ch.shape[1]), sr=sr, hop_length=hop)
    cel = np.floor(2 * np.interp(t, bt, idx) + EPS).astype(int)
    lo = int(2 * idx[0])
    n = int(2 * idx[-1]) - lo + 1
    out = np.zeros((n, 12))
    ok = (cel >= lo) & (cel < lo + n)
    np.add.at(out, cel[ok] - lo, ch[:, ok].T)
    np.save(arq, out)
    return out


def fidelidade(md, me, pasta: Path, desloc: float, bt, idx, regioes=()) -> dict:
    import pretty_midi
    aud = croma_audio(pasta, bt, idx)
    md, me = com_pedal(md, regioes), com_pedal(me, regioes)
    lo, n = int(2 * idx[0]), len(aud)
    notas = [(2 * (o - desloc) - lo, 2 * (o + d - desloc) - lo, p) for o, d, ps in md + me for p in ps]
    r = dict(croma_audio=round(_cos(_croma_notas(notas, n), aud), 4))
    mid = pasta / "cache" / "amtapc_medio.mid"
    if mid.exists():
        ia = [nn for i in pretty_midi.PrettyMIDI(str(mid)).instruments for nn in i.notes]
        g = lambda t: 2 * float(np.interp(t, bt, idx)) - lo
        r["croma_audio_ia"] = round(_cos(_croma_notas([(g(x.start), g(x.end), x.pitch) for x in ia], n), aud), 4)
        # ataques em segundos: partitura pela grade, IA direto
        t_partitura = sorted((float(np.interp(o - desloc, idx, bt)), p) for o, d, ps in md + me for p in ps)
        t_ia = sorted((x.start, x.pitch) for x in ia)
        acertos = _casar(t_partitura, t_ia, .15)
        r["recall_ia"] = round(acertos / max(1, len(t_ia)), 4)
        r["precisao_ia"] = round(acertos / max(1, len(t_partitura)), 4)
    return r


def _casar(a, b, tol):
    """Pares (tempo, altura) casados um a um com |Δt| <= tol, mesma altura (guloso por altura)."""
    from collections import defaultdict
    pa, pb = defaultdict(list), defaultdict(list)
    for t, p in a:
        pa[p].append(t)
    for t, p in b:
        pb[p].append(t)
    total = 0
    for p, ta in pa.items():
        tb = pb.get(p)
        if not tb:
            continue
        i = j = 0
        while i < len(ta) and j < len(tb):
            if abs(ta[i] - tb[j]) <= tol:
                total += 1
                i += 1
                j += 1
            elif ta[i] < tb[j]:
                i += 1
            else:
                j += 1
    return total


# ------------------------------------------------------------------ tudo junto

def medir_xml(xml: Path, nivel: str, pasta: Path) -> dict:
    from avaliar_maos import eventos_da_partitura
    import gerar
    texto = xml.read_text(encoding="utf-8")
    md, me, bpm, _ = eventos_da_partitura(xml)
    md = [(o, d, ps) for o, d, ps in md if ps]
    me = [(o, d, ps) for o, d, ps in me if ps]
    r = leitura(texto)
    n = max(1, sum(len(ps) for _, _, ps in md + me))
    r["notas"] = n
    r.update(tocabilidade(md, me, bpm))
    sinc = json.loads((pasta / "cache" / "sincronia_original.json").read_text(encoding="utf-8"))
    desloc = float(sinc["versoes"].get(f"AMT-APC - {xml.stem.split(' - ')[-1]}", 0.0))
    bt, idx = np.array(sinc["bt"]), np.array(sinc["idx"])
    tr = json.loads((pasta / "cache" / "transcricao.json").read_text(encoding="utf-8"))
    r.update(som(md, me, tr["acordes"], desloc, gerar.TIPOS))
    r.update(fidelidade(md, me, pasta, desloc, bt, idx, pedais(texto)))
    r["bpm"] = round(bpm, 1)
    r["duracao_s"] = round(max([o + d for o, d, _ in md + me] or [0]) * 60 / bpm, 1)
    return r
