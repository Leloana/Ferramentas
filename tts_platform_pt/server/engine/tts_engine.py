import logging
import os

os.environ.setdefault("COQUI_TOS_AGREED", "1")

import torch
from TTS.api import TTS

import config

logger = logging.getLogger("TTSPlatform")


class TTSEngine:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            self.tts = TTS(config.XTTS_MODEL_NAME).to(self.device)
        except Exception as e:
            logger.warning(f"Falha ao carregar XTTS-v2 na GPU ({e}), caindo para CPU.")
            self.device = "cpu"
            self.tts = TTS(config.XTTS_MODEL_NAME).to("cpu")
        logger.info(f"XTTS-v2 carregado no dispositivo: {self.device}")

    def list_builtin_speakers(self):
        return list(self.tts.speakers or [])

    def synthesize(self, text, output_path, language=config.DEFAULT_LANGUAGE, speaker=None, speaker_wav=None):
        kwargs = {"text": text, "file_path": str(output_path), "language": language}
        if speaker_wav:
            kwargs["speaker_wav"] = str(speaker_wav)
        else:
            builtin = self.list_builtin_speakers()
            kwargs["speaker"] = speaker or (builtin[0] if builtin else None)
        self.tts.tts_to_file(**kwargs)
        return output_path


_engine = None


def get_tts_engine():
    global _engine
    if _engine is None:
        _engine = TTSEngine()
    return _engine
