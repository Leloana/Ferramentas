"""Arranjo de piano completo com o Pop2Piano (sweetcocoa/pop2piano), na mesma grade de batidas.

O Pop2Piano escuta a mixagem inteira e "toca um cover": melodia + acompanhamento juntos.
Aqui o MIDI dele é quantizado, dividido em mão direita/esquerda e vira partitura.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI / "_stubs"))  # essentia falso (só batidas), precisa vir antes do transformers


def _por_mao(notas, grade, passo):
    """Agrupa notas que começam juntas em acordes; sem sobreposição dentro da mão."""
    grupos: dict[float, list] = {}
    for n in notas:
        a = grade.q(n.start)
        b = max(grade.q(n.end), a + passo)
        grupos.setdefault(a, []).append((b, n.pitch))
    inicios = sorted(grupos)
    ev = []
    for i, a in enumerate(inicios):
        fim = min(b for b, _ in grupos[a])
        if i + 1 < len(inicios):
            fim = min(fim, inicios[i + 1])
        ps = sorted({p for _, p in grupos[a]})
        if len(ps) > 4:  # mão humana: no máximo 4 notas, mantém extremos
            ps = [ps[0], ps[1], ps[-2], ps[-1]]
        ev.append((a, fim - a, ps))
    return ev


def arranjo(audio: Path, base: Path, titulo: str, subtitulo: str, grade, bpm: float, cifras,
            compositor: str = "composer1"):
    import librosa
    import torch
    import essentia.standard as es_stub
    from transformers import Pop2PianoForConditionalGeneration, Pop2PianoProcessor

    import gerar

    print(f"[pop2piano] carregando modelo ({compositor})...")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    modelo = Pop2PianoForConditionalGeneration.from_pretrained("sweetcocoa/pop2piano").to(dev)
    proc = Pop2PianoProcessor.from_pretrained("sweetcocoa/pop2piano")

    y, sr = librosa.load(str(audio), sr=44100, mono=True)
    es_stub.BATIDAS = grade.bt
    es_stub.SR = sr
    entrada = proc(audio=y, sampling_rate=sr, return_tensors="pt")
    with torch.no_grad():
        saida = modelo.generate(input_features=entrada["input_features"].to(dev), composer=compositor)
    pm = proc.batch_decode(token_ids=saida.cpu(), feature_extractor_output=entrada)["pretty_midi_objects"][0]

    mid_bruto = base.with_name(base.name + "_pop2piano_bruto.mid")
    pm.write(str(mid_bruto))
    notas = [n for inst in pm.instruments for n in inst.notes]
    print(f"[pop2piano] {len(notas)} notas geradas")

    passo = 1 / gerar.SR_GRADE
    md = _por_mao([n for n in notas if n.pitch >= 60], grade, passo)
    me = _por_mao([n for n in notas if n.pitch < 60], grade, passo)
    sc, k = gerar.montar_partitura(md, me, cifras, bpm, titulo + " (arranjo Pop2Piano)", subtitulo)

    b = base.with_name(base.name + "_pop2piano")
    xml, mid, pdf = b.with_suffix(".musicxml"), b.with_suffix(".mid"), b.with_suffix(".pdf")
    sc.write("musicxml", fp=str(xml))
    sc.write("midi", fp=str(mid))
    n = gerar.xml_para_pdf(xml, pdf)
    gerar.midi_para_mp3(mid_bruto, b.with_name(b.name + "_previa.mp3"))
    print(f"[ok] {pdf} ({n} páginas, armadura {k})")
