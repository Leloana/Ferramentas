import logging
import os
import re
import string
import sys

import numpy as np
from rapidfuzz import fuzz

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

# Limiar absoluto mínimo: palavras abaixo disso são quase certamente alucinações
# mesmo em contexto de canto. Sobe em degraus com o no_speech_prob.
_HARD_FLOOR = 0.05

# Confiança média abaixo disso com a letra como initial_prompt = o Whisper
# provavelmente copiou a dica em vez de ouvir. Calibrado nas partidas de
# 2026-09-29: alucinações ficaram em 0,08–0,09; canto certo tem mediana 0,84.
PROMPT_TRUST_MIN_PROB = 0.2


def prompted_words_trusted(words: list[dict]) -> bool:
    """Palavras transcritas com a letra como dica merecem confiança? (vazio = nada a checar)"""
    if not words:
        return True
    return float(np.mean([w["probability"] for w in words])) >= PROMPT_TRUST_MIN_PROB


def pick_transcription(prompted_words: list[dict] | None,
                       unprompted_words: list[dict] | None) -> tuple[list[dict], str | None]:
    """Mesmo portão do ao vivo: (palavras, "prompted" | "unprompted" | None).

    Com dica e confiável vale a passada com dica; sem confiança (ou sem dica) vale
    a sem dica. Usado pelo `transcribe` e pela repontuação das partidas gravadas.
    """
    if prompted_words is not None and (unprompted_words is None or prompted_words_trusted(prompted_words)):
        return prompted_words, "prompted"
    if unprompted_words is not None:
        return unprompted_words, "unprompted"
    return [], None


def _get_word_threshold(no_speech_prob: float) -> float:
    """Retorna o limiar de probabilidade de palavra aceitável baseado no no_speech_prob do segmento.

    Calibrado para canto com acompanhamento instrumental, onde o Whisper produz
    estruturalmente probabilidades por palavra mais baixas do que em fala limpa.
    O no_speech_prob em canto tipicamente fica entre 0.10–0.30 mesmo com voz
    presente, então os limiares precisam ser mais permissivos nessa faixa.
    """
    if no_speech_prob > 0.60:
        return max(0.50, _HARD_FLOOR)  # Quase certo silêncio/ruído: exigente mas não intransponível
    elif no_speech_prob > 0.40:
        return max(0.30, _HARD_FLOOR)  # Provável silêncio/ruído
    elif no_speech_prob > 0.25:
        return max(0.18, _HARD_FLOOR)  # Ruído moderado (faixa típica de canto com instrumental pesado)
    elif no_speech_prob > 0.15:
        return max(0.18, _HARD_FLOOR)  # Canto com instrumental (faixa mais comum: 0.15–0.25)
    else:
        return max(0.08, _HARD_FLOOR)  # Canto relativamente limpo

# large-v3-turbo: encoder do large-v3 com decoder de 4 camadas. Erra menos que o
# medium e decodifica mais rápido que ele; ~2 GB de VRAM em float16.
DEFAULT_WHISPER_MODEL = "large-v3-turbo"
DEFAULT_COMPUTE = {"cuda": "float16", "cpu": "int8"}


def _r(value, digits: int = 4):
    """Arredonda para o JSON da gravação (None fica None)."""
    try:
        return None if value is None else round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _raw_segment(segment, text: str) -> dict | None:
    """Segmento do Whisper para a gravação. Nunca atrapalha a transcrição."""
    try:
        g = lambda obj, name: _r(getattr(obj, name, None))  # noqa: E731
        return {
            "text": text,
            "start": g(segment, "start"), "end": g(segment, "end"),
            "no_speech_prob": g(segment, "no_speech_prob"),
            "avg_logprob": g(segment, "avg_logprob"),
            "compression_ratio": g(segment, "compression_ratio"),
            "temperature": g(segment, "temperature"),
            "words": [
                {"word": str(getattr(w, "word", "")).strip(), "start": g(w, "start"), "end": g(w, "end"),
                 "probability": g(w, "probability")}
                for w in (getattr(segment, "words", None) or [])
            ],
        }
    except Exception:
        return None


class STTEngine:
    def __init__(self, model_size=None, device=None, compute_type=None):
        """Carrega o Whisper. Sem argumento, lê do ambiente:

        KARAOKE_WHISPER_MODEL   — nome do faster-whisper (padrão large-v3-turbo)
        KARAOKE_WHISPER_DEVICE  — auto | cuda | cpu (padrão auto: tenta CUDA, cai na CPU)
        KARAOKE_WHISPER_COMPUTE — força o compute_type (padrão float16 na GPU, int8 na CPU)
        """
        self.model_size = model_size or os.environ.get("KARAOKE_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
        device = device or os.environ.get("KARAOKE_WHISPER_DEVICE", "auto")
        self.compute_override = compute_type or os.environ.get("KARAOKE_WHISPER_COMPUTE") or None

        if device in ("auto", "cuda"):
            try:
                self._load("cuda")
                return
            except Exception as e:
                logger.warning(f"Falha ao carregar Whisper '{self.model_size}' com CUDA: {e}. Tentando CPU...")
        try:
            self._load("cpu")
        except Exception as e:
            logger.error(f"Erro fatal ao carregar Whisper '{self.model_size}': {e}")
            raise e

    def _load(self, device: str) -> None:
        compute = self.compute_override or DEFAULT_COMPUTE[device]
        logger.info(f"Carregando Whisper '{self.model_size}' em {device} ({compute})...")
        self.model = WhisperModel(self.model_size, device=device, compute_type=compute)
        self.device = device
        logger.info(f"Whisper '{self.model_size}' carregado em {device}.")

    def transcribe(self, audio_data, language, initial_prompt=None, rms_threshold=0.001, expected_words=None,
                   details: dict | None = None):
        """(texto, palavras) da passada que vale.

        `details` (opcional) recebe as duas passadas para o gravador:
        {"prompted_words", "unprompted_words", "used"} — None na que não rodou;
        `used` é None quando o trecho era silêncio e o Whisper nem rodou.
        """
        raw = None
        if details is not None:
            details.update(prompted_words=None, unprompted_words=None, used=None)
            # dados crus de cada passada (gravação completa): segmentos com
            # no_speech_prob/avg_logprob, idioma e TODAS as palavras, inclusive
            # as descartadas pelo filtro de confiança (tempos relativos ao trecho)
            raw = details.setdefault("raw", [])
        rms = np.sqrt(np.mean(audio_data ** 2)) if len(audio_data) > 0 else 0
        if rms < rms_threshold:
            logger.info(f"Trecho silencioso detectado (RMS: {rms:.5f}). Ignorando Whisper para prevenir alucinações.")
            return "", []

        text, words = self._transcribe_once(audio_data, language, initial_prompt, expected_words, raw)
        if not initial_prompt:
            if details is not None:
                details.update(unprompted_words=words, used="unprompted")
            return text, words
        prompted_text, prompted = text, words
        unprompted = None

        # Com a letra como dica e áudio confuso (cantarolar, murmurar), o Whisper
        # devolve a própria dica com confiança quase nula e o verso tira 100.
        # Segunda opinião sem dica: vale o que de fato foi ouvido.
        if not prompted_words_trusted(prompted):
            logger.info(
                f"🔁 [Dica suspeita] '{text}' com confiança média < {PROMPT_TRUST_MIN_PROB}: "
                f"transcrevendo de novo sem a letra como dica"
            )
            text, unprompted = self._transcribe_once(audio_data, language, None, expected_words, raw)
        words, used = pick_transcription(prompted, unprompted)
        if used == "prompted":
            text = prompted_text
        if details is not None:
            details.update(prompted_words=prompted, unprompted_words=unprompted, used=used)
        return text, words

    def _transcribe_once(self, audio_data, language, initial_prompt, expected_words, raw: list | None = None):
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
            raw_run = None
            if raw is not None:
                raw_run = {
                    "prompted": bool(initial_prompt),
                    "language": getattr(info, "language", None),
                    "language_probability": _r(getattr(info, "language_probability", None)),
                    "duration_after_vad": _r(getattr(info, "duration_after_vad", None)),
                    "segments": [],
                }
                raw.append(raw_run)

            for segment in segments:
                text_clean = segment.text.strip()
                raw_seg = _raw_segment(segment, text_clean) if raw_run is not None else None
                if raw_seg is not None:
                    raw_run["segments"].append(raw_seg)

                if _HALLUCINATION_RE.search(text_clean):
                    logger.info(f"Alucinação do Whisper detectada e expurgada: '{text_clean}'")
                    if raw_seg is not None:
                        raw_seg["dropped"] = "hallucination"
                    continue

                no_speech_prob = getattr(segment, "no_speech_prob", 0.0)
                word_threshold = _get_word_threshold(no_speech_prob)

                # Pré-limpa as palavras esperadas para o whitelist check
                clean_expected = None
                if expected_words:
                    clean_expected = [
                        w.lower().strip().translate(str.maketrans("", "", string.punctuation))
                        for w in expected_words
                    ]

                if segment.words:
                    for word in segment.words:
                        word_clean = word.word.strip()
                        if _HALLUCINATION_RE.search(word_clean):
                            continue

                        # Whitelist: palavras esperadas (ex.: neologismos, nomes próprios)
                        # são aceitas mesmo com baixa confiança do Whisper
                        whitelisted = False
                        if clean_expected:
                            word_key = word_clean.lower().translate(
                                str.maketrans("", "", string.punctuation)
                            )
                            # Japonês vem em pedaços de 1–3 caracteres ("遠", "ざ"): vale
                            # estar dentro de alguma palavra da letra.
                            if word_key and language and language.lower().startswith("ja") \
                                    and any(word_key in exp for exp in clean_expected):
                                whitelisted = True
                            for exp in ([] if whitelisted else clean_expected):
                                if fuzz.ratio(word_key, exp) >= 80:
                                    whitelisted = True
                                    logger.info(
                                        f"✅ [Whitelist] Palavra '{word_clean}' aceita por match fuzzy "
                                        f"com esperada '{exp}' (ratio={fuzz.ratio(word_key, exp)}, "
                                        f"prob={word.probability:.3f}, limiar={word_threshold})"
                                    )
                                    break

                        # Filtro de confiança adaptativo baseando-se no ruído/silêncio do segmento
                        if not whitelisted and word.probability < word_threshold:
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
                # O compute forçado pode ser só de GPU (ex.: int8_float16): na CPU vale o padrão dela.
                self.compute_override = None
                self._load("cpu")
                return self._transcribe_once(audio_data, language, initial_prompt, expected_words)
            raise e

# Singleton para uso no servidor
engine = None

def get_stt_engine():
    global engine
    if engine is None:
        engine = STTEngine()
    return engine
