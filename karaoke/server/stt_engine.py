import logging
import os
import re
import sys

import numpy as np

# Padrões de alucinação conhecidos do Whisper (legendas/agradecimentos genéricos
# que vazam do dataset de treinamento). Compilado uma única vez.
_HALLUCINATION_RE = re.compile(
    r"thanks?\s+for\s+(watching|sharing|playing|the\s+video|this\s+video)|"
    r"thank\s+you\s+for\s+(watching|sharing)|"
    r"subscribe\s+to\s+my\s+channel|"
    r"please\s+subscribe|"
    r"amara\.org|"
    r"legendas\s+pela|"
    r"legendas\s+por|"
    r"subtitles\s+by|"
    r"translated\s+by|"
    r"watching\s+this\s+video",
    re.IGNORECASE,
)

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Se for Windows, registra as DLLs das rodas da NVIDIA do venv no DLL search path
if sys.platform == "win32":
    venv_dir = os.path.dirname(os.path.dirname(sys.executable))
    venv_site_packages = os.path.join(venv_dir, "Lib", "site-packages")
    if os.path.exists(venv_site_packages):
        nvidia_base = os.path.join(venv_site_packages, "nvidia")
        if os.path.exists(nvidia_base):
            logger.info("Localizado diretório NVIDIA no venv. Registrando DLLs no search path...")
            registered_dirs = 0
            for root, dirs, files in os.walk(nvidia_base):
                if "bin" in dirs:
                    bin_dir = os.path.join(root, "bin")
                    if any(f.endswith(".dll") for f in os.listdir(bin_dir)):
                        logger.info(f"Registrando diretório de DLL: {bin_dir}")
                        os.add_dll_directory(bin_dir)
                        registered_dirs += 1
            if registered_dirs == 0:
                logger.debug("Nenhum diretório com DLLs do CUDA foi encontrado dentro de 'nvidia'.")
        else:
            logger.debug(f"Diretório base 'nvidia' não encontrado em: {venv_site_packages}")
    else:
        logger.debug("Não foi possível localizar o diretório venv site-packages para buscar as DLLs do CUDA.")

# Importa faster_whisper após registrar as DLLs
from faster_whisper import WhisperModel

def _get_word_threshold(no_speech_prob: float) -> float:
    """Retorna o limiar de probabilidade de palavra aceitável baseado no no_speech_prob do segmento."""
    if no_speech_prob > 0.60:
        return 0.70  # Segmento quase certamente silencioso ou com ruído. Exige alta certeza.
    elif no_speech_prob > 0.40:
        return 0.55  # Alta probabilidade de silêncio/ruído.
    elif no_speech_prob > 0.25:
        return 0.45  # Ruído moderado / possível silêncio.
    elif no_speech_prob > 0.15:
        return 0.35  # Baixo ruído, provável voz.
    else:
        return 0.25  # Áudio limpo, permite palavras com pronúncia rápida.

class STTEngine:
    def __init__(self, model_size="medium", device="auto", compute_type="default"):
        """
        device: "cuda", "cpu" ou "auto"
        """
        self.model_size = model_size
        # Se device for auto, tenta cuda primeiro
        if device == "auto":
            try:
                logger.info(f"Tentando carregar modelo Whisper '{model_size}' com CUDA...")
                self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
                logger.info("Modelo carregado com CUDA com sucesso!")
                return
            except Exception as e:
                logger.warning(f"Falha ao carregar CUDA: {e}. Tentando CPU...")
        
        # Fallback para CPU
        try:
            logger.info(f"Carregando modelo Whisper '{model_size}' com CPU...")
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
            logger.info("Modelo carregado com CPU com sucesso.")
        except Exception as e:
            logger.error(f"Erro fatal ao carregar Whisper: {e}")
            raise e

    def transcribe(self, audio_data, language, initial_prompt=None, rms_threshold=0.001):
        rms = np.sqrt(np.mean(audio_data ** 2)) if len(audio_data) > 0 else 0
        if rms < rms_threshold:
            logger.info(f"Trecho silencioso detectado (RMS: {rms:.5f}). Ignorando Whisper para prevenir alucinações.")
            return "", []

        try:
            segments, info = self.model.transcribe(
                audio_data, 
                language=language, 
                word_timestamps=True,
                beam_size=5,
                initial_prompt=initial_prompt,
                vad_filter=True
            )

            full_text = ""
            words_list = []

            for segment in segments:
                text_clean = segment.text.strip()

                if _HALLUCINATION_RE.search(text_clean):
                    logger.info(f"Alucinação do Whisper detectada e expurgada: '{text_clean}'")
                    continue

                no_speech_prob = getattr(segment, "no_speech_prob", 0.0)
                word_threshold = _get_word_threshold(no_speech_prob)

                if segment.words:
                    for word in segment.words:
                        word_clean = word.word.strip()
                        if _HALLUCINATION_RE.search(word_clean):
                            continue
                        
                        # Filtro de confiança adaptativo baseando-se no ruído/silêncio do segmento
                        if word.probability < word_threshold:
                            logger.info(
                                f"🚫 [Filtro Confiança] Descartando palavra incerta/alucinada '{word_clean}' "
                                f"(prob={word.probability:.3f} < limiar={word_threshold} para no_speech_prob={no_speech_prob:.3f})"
                            )
                            continue

                        words_list.append({
                            "word": word_clean,
                            "start": word.start,
                            "end": word.end,
                            "probability": word.probability,
                        })

            full_text = " ".join([w["word"] for w in words_list])
            return full_text.strip(), words_list
        except RuntimeError as e:
            if "cublas" in str(e).lower() or "cudnn" in str(e).lower():
                logger.warning("Erro de biblioteca CUDA detectado durante execução. Trocando para CPU...")
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                return self.transcribe(audio_data, language, initial_prompt=initial_prompt)
            raise e

# Singleton para uso no servidor
engine = None

def get_stt_engine():
    global engine
    if engine is None:
        # Usamos 'auto' para tentar GPU se disponível, senão CPU
        engine = STTEngine(device="auto")
    return engine
