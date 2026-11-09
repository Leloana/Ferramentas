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


def notas_pop2piano(audio: Path, base: Path, grade, compositor: str = "composer1"):
    """Notas (pretty_midi) do cover gerado. Fica em cache em <pasta>/cache/pop2piano_bruto.mid."""
    import pretty_midi

    mid_bruto = base / "cache" / "pop2piano_bruto.mid"
    mid_bruto.parent.mkdir(parents=True, exist_ok=True)
    if mid_bruto.exists():
        print(f"[pop2piano] usando cache {mid_bruto.name}")
        pm = pretty_midi.PrettyMIDI(str(mid_bruto))
    else:
        import librosa
        import torch
        import essentia.standard as es_stub
        from transformers import Pop2PianoForConditionalGeneration, Pop2PianoProcessor

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
        pm.write(str(mid_bruto))
    notas = [n for inst in pm.instruments for n in inst.notes]
    print(f"[pop2piano] {len(notas)} notas")
    return notas, mid_bruto


def mao_esquerda(audio: Path, base: Path, grade, corte: int = 60):
    """Só o acompanhamento do Pop2Piano (notas abaixo de `corte`), pra versão híbrida."""
    import gerar
    notas, _ = notas_pop2piano(audio, base, grade)
    return _por_mao([n for n in notas if n.pitch < corte], grade, 1 / gerar.SR_GRADE)


def maos_pop2piano(audio: Path, base: Path, grade):
    """(mão direita, mão esquerda) do Pop2Piano quantizadas na grade atual (gerar.SR_GRADE)."""
    import gerar
    notas, _ = notas_pop2piano(audio, base, grade)
    passo = 1 / gerar.SR_GRADE
    return (_por_mao([n for n in notas if n.pitch >= 60], grade, passo),
            _por_mao([n for n in notas if n.pitch < 60], grade, passo))
