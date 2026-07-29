from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
VOICES_DIR = SERVER_DIR / "voices"
CUSTOM_VOICES_DIR = VOICES_DIR / "custom"
OUTPUT_DIR = SERVER_DIR / "output"

HOST = "127.0.0.1"
PORT = 8010

XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
DEFAULT_LANGUAGE = "pt"

OLLAMA_MODEL = "gemma3n:e4b"

CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
