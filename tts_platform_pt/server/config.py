from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
VOICES_DIR = SERVER_DIR / "voices"
CUSTOM_VOICES_DIR = VOICES_DIR / "custom"
OUTPUT_DIR = SERVER_DIR / "output"

HOST = "127.0.0.1"
PORT = 8010

XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
DEFAULT_LANGUAGE = "pt"

OLLAMA_MODEL = "qwen3:0.6b"

# O tamanho do contexto domina o uso de VRAM no Ollama, não a contagem de
# parâmetros do modelo (num_ctx=40960 padrão do Qwen3 consome ~5GB de VRAM
# sozinho). Em vez de um valor fixo, o contexto é escolhido dinamicamente a
# cada chamada com base na VRAM livre no momento (ver engine/text_preprocessor.py),
# reservando espaço pro XTTS-v2 e caindo pro maior patamar que couber. Se não
# sobrar nem o mínimo, a normalização é pulada (o áudio sai sem ela, com aviso
# ao usuário) em vez de arriscar um OOM na GPU.
#
# Patamares medidos nesta máquina (RTX 4070, 12GB, qwen3:0.6b):
#   4096 -> ~1.0GB | 8192 -> ~1.5GB | 16384 -> ~2.5GB | 32768 -> ~4.4GB
OLLAMA_NUM_CTX_TIERS_MB = [
    (32768, 4400),
    (16384, 2500),
    (8192, 1500),
    (4096, 1000),
]
OLLAMA_XTTS_RESERVE_MB = 3072  # folga reservada pro XTTS-v2, carregado ou não
OLLAMA_MIN_FREE_MB = 1200  # abaixo disso, nem tenta o menor patamar

# Usado só quando não há GPU disponível (sem disputa de VRAM entre os dois).
OLLAMA_NUM_CTX_CPU_FALLBACK = 8192

CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
