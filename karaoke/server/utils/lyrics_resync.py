"""Letra trocada no editor ("Letra" colada) → LRC novo encaixado no áudio.

O "Gerar segments" refazia só as palavras do `lyrics.lrc` que já existia: colar a
letra certa na aba "Letra" não mudava nada na tela. Quando o texto da letra não
bate mais com o do LRC (e o LRC não foi mexido à mão), o LRC sai do plano por
estrutura (`lrc_sync.sync_lrc`: Whisper do stem × letra), como na primeira vez.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from utils.lrc_pro import parse_synced_lrc

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "tools"


def _key(line: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", line.lower()).split())


def _plain_keys(plain: str) -> set[str]:
    # mesmo filtro do sync_lrc: cabeçalho "[Refrão]" não é verso
    return {_key(ln) for ln in plain.splitlines()
            if _key(ln) and not (ln.strip().startswith("[") and "]" in ln)}


def plain_differs_from_lrc(lrc_text: str | None, plain: str | None) -> bool:
    """A letra tem verso que o LRC não tem (ou o contrário)? Repetição não conta:
    o LRC pode cantar o refrão mais vezes que a letra escreve."""
    if not plain or not _plain_keys(plain):
        return False
    lrc_keys = {_key(ln["text"]) for ln in parse_synced_lrc(lrc_text or "")} - {""}
    return lrc_keys != _plain_keys(plain)


def lrc_from_plain(song_dir: Path, plain: str, language: str) -> str | None:
    """LRC da letra encaixado na voz separada (None: não deu para encaixar)."""
    if str(_TOOLS_DIR) not in sys.path:
        sys.path.append(str(_TOOLS_DIR))
    from pydub import AudioSegment

    from reinstall_song import _structure_transcriber  # import tardio: Whisper
    from utils.audio import vocal_to_float32_mono_16k
    from utils.lrc_sync import sync_lrc

    audio = vocal_to_float32_mono_16k(AudioSegment.from_file(song_dir / "vocal.mp3"))
    res = sync_lrc(None, plain, audio, language, _structure_transcriber(language, song_dir))
    return res.lrc_text
