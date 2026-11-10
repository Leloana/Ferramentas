"""Versão "Híbrido Gravado": a mão esquerda com o que o piano e o violão TOCARAM na gravação.

Em vez de uma IA de "piano cover" (Pop2Piano, AMT-APC), que rearranja, aqui as faixas de
piano e de violão/guitarra do Demucs de 6 faixas (`htdemucs_6s`) são transcritas nota a nota:
- piano: piano_transcription_inference (Kong et al. 2020, ByteDance; checkpoint em
  modelos/piano_transcription/, baixado do Zenodo record 4034264);
- violão/guitarra: Basic Pitch (Spotify, 2022; modelo ONNX que vem no pacote).
As duas viram um MIDI só (cache/gravado.mid). Na partitura: melodia cantada com letra na
direita (+ a direita instrumental nas lacunas da voz, como no Híbrido AMT) e, na esquerda, as
notas graves transcritas. O piano costuma tocar só em trechos, então compasso sem nada
transcrito recebe a esquerda da versão Acordes. Sem LLM.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CHECKPOINT = AQUI / "modelos" / "piano_transcription" / "note_F1=0.9677_pedal_F1=0.9186.pth"
SEPARADOS = AQUI / "trabalho" / "htdemucs_6s"


def faixas_6(audio: Path) -> Path:
    """Pasta com piano.wav/guitar.wav do htdemucs_6s (cache em trabalho/htdemucs_6s/<nome>/)."""
    pasta = SEPARADOS / audio.stem
    if not (pasta / "piano.wav").exists():
        print("[gravado] separando em 6 faixas (htdemucs_6s)...", flush=True)
        subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs_6s", "-o", str(SEPARADOS.parent),
                        str(audio)], check=True)
    return pasta


def _piano(wav: Path, destino: Path):
    import librosa
    import torch
    from piano_transcription_inference import PianoTranscription, sample_rate
    x, _ = librosa.load(str(wav), sr=sample_rate, mono=True)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    PianoTranscription(device=dev, checkpoint_path=str(CHECKPOINT)).transcribe(x, str(destino))


def _violao(wav: Path, destino: Path):
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict
    # violão: nota curta demais e altíssima costuma ser ruído/harmônico
    _, midi, _ = predict(str(wav), ICASSP_2022_MODEL_PATH, minimum_note_length=80,
                         minimum_frequency=70, maximum_frequency=1400)
    midi.write(str(destino))


def midi_gravado(audio: Path, pasta: Path) -> Path:
    """MIDI com piano + violão transcritos (cache em <pasta>/cache/gravado.mid)."""
    import pretty_midi
    destino = pasta / "cache" / "gravado.mid"
    if destino.exists():
        print(f"[gravado] usando cache {destino.name}")
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    faixas = faixas_6(audio)
    p_mid, v_mid = destino.with_name("gravado_piano.mid"), destino.with_name("gravado_violao.mid")
    if not p_mid.exists():
        print("[gravado] transcrevendo o piano (Kong et al.)...", flush=True)
        _piano(faixas / "piano.wav", p_mid)
    if not v_mid.exists():
        print("[gravado] transcrevendo o violão/guitarra (Basic Pitch)...", flush=True)
        _violao(faixas / "guitar.wav", v_mid)
    saida = pretty_midi.PrettyMIDI()
    for arq, nome in ((p_mid, "piano"), (v_mid, "violao")):
        inst = pretty_midi.Instrument(program=0, name=nome)
        for i in pretty_midi.PrettyMIDI(str(arq)).instruments:
            inst.notes += [n for n in i.notes if n.velocity >= 25]   # fantasma de vazamento entre faixas
        saida.instruments.append(inst)
    saida.write(str(destino))
    return destino


def maos_gravado(audio: Path, pasta: Path, grade):
    """(direita, esquerda) quantizadas na grade atual, como no AMT-APC."""
    import pretty_midi
    from pop2piano import _por_mao
    pm = pretty_midi.PrettyMIDI(str(midi_gravado(audio, pasta)))
    notas = [n for inst in pm.instruments for n in inst.notes]
    return (_por_mao([n for n in notas if n.pitch >= 60], grade, grade.passo),
            _por_mao([n for n in notas if n.pitch < 60], grade, grade.passo))


def completar_com(esquerda, reserva, compasso=4.0):
    """Compasso sem nenhuma nota na esquerda transcrita recebe os eventos da reserva (Acordes)."""
    ocupados = {int(o // compasso) for o, d, ps, *_ in esquerda if ps}
    extra = [e for e in reserva if int(e[0] // compasso) not in ocupados]
    return sorted(list(esquerda) + extra, key=lambda e: e[0]), len({int(e[0] // compasso) for e in extra})
