import json
import os
from pathlib import Path
from typing import Any, Dict, List

CONFIG_DIR = Path(__file__).resolve().parent
CONFIG_PATH = CONFIG_DIR / "config.json"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "config.example.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
        "password": "change_me_123",
        "session_secret": "session_secret_change_me_super_secret"
    },
    "llm": {
        "provider": "ollama",  # ollama | openai | gemini | anthropic | openrouter | groq | custom
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "",
        "model": "qwen3.5:9b",
        "temperature": 0.4
    },
    "apps": [
        {
            "id": "tts_platform_pt",
            "name": "Plataforma de TTS & Vídeos",
            "port": 8011,
            "url": "http://127.0.0.1:8011",
            "desc": "Síntese XTTS-v2 e Produção de Vídeos 9:16"
        },
        {
            "id": "comfyui",
            "name": "ComfyUI Desktop",
            "port": 8188,
            "url": "http://127.0.0.1:8188",
            "desc": "Workflows de Imagem e Qwen-Image-2.1"
        },
        {
            "id": "karaoke",
            "name": "Karaoke AI Premium",
            "port": 8000,
            "url": "http://127.0.0.1:8000",
            "desc": "Separação de faixas e console de karaokê"
        },
        {
            "id": "testing_space",
            "name": "Testing Space (Snooker)",
            "port": 8080,
            "url": "http://127.0.0.1:8080",
            "desc": "Espaço de experimentos web"
        }
    ],
    "terminal": {
        "allowed_commands": [
            "git",
            "nvidia-smi",
            "ollama",
            "python",
            "python3",
            "uvicorn",
            "ls",
            "dir",
            "pwd",
            "whoami",
            "echo"
        ],
        "quick_actions": [
            {"label": "VRAM Status", "cmd": "nvidia-smi"},
            {"label": "Ollama Models", "cmd": "ollama ps"},
            {"label": "Git Status", "cmd": "git status"},
            {"label": "Git Log", "cmd": "git log -n 5 --oneline"},
            {"label": "Git Pull", "cmd": "git pull"}
        ]
    },
    "cloudflare": {
        "enabled": True,
        "mode": "quick",
        "tunnel_token": ""
    }
}


def load_config() -> Dict[str, Any]:
    """Loads configuration from config.json or environment variables, falling back to defaults."""
    cfg = DEFAULT_CONFIG.copy()

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                _deep_update(cfg, user_cfg)
        except Exception as e:
            print(f"[config] Aviso ao ler {CONFIG_PATH}: {e}")
    elif EXAMPLE_CONFIG_PATH.exists():
        try:
            with open(EXAMPLE_CONFIG_PATH, "r", encoding="utf-8") as f:
                example_cfg = json.load(f)
                _deep_update(cfg, example_cfg)
        except Exception:
            pass

    # Environment variables override
    if os.getenv("AGENT_REMOTE_PASSWORD"):
        cfg["server"]["password"] = os.getenv("AGENT_REMOTE_PASSWORD")
    if os.getenv("AGENT_REMOTE_PORT"):
        cfg["server"]["port"] = int(os.getenv("AGENT_REMOTE_PORT"))
    if os.getenv("LLM_PROVIDER"):
        cfg["llm"]["provider"] = os.getenv("LLM_PROVIDER")
    if os.getenv("LLM_API_KEY"):
        cfg["llm"]["api_key"] = os.getenv("LLM_API_KEY")
    if os.getenv("LLM_MODEL"):
        cfg["llm"]["model"] = os.getenv("LLM_MODEL")
    if os.getenv("LLM_BASE_URL"):
        cfg["llm"]["base_url"] = os.getenv("LLM_BASE_URL")

    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    """Saves updated config to config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _deep_update(base: dict, update: dict) -> dict:
    for k, v in update.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base
