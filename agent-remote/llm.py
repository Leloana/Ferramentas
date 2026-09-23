import json
import os
from typing import AsyncGenerator, Dict, List, Optional
import httpx
from config import load_config

DEFAULT_SYSTEM_PROMPT = """Você é o Assistente Remoto do repositório Ferramentas.
Você opera a partir de uma interface web conectada à máquina do usuário.
Você tem acesso às ferramentas do repositório, como:
- tts_platform_pt (Síntese XTTS-v2, ComfyUI com Qwen-Image-2.1 e montagem de vídeos 9:16)
- karaoke (Karaoke AI com separação Demucs e alinhamento MMS_FA)
- youtube_music_playlist_organizer (Classificação de músicas via IA)
- docx_to_pdf_converter e local_agent

Você pode sugerir comandos seguros da whitelist para o usuário rodar no terminal web (como git status, nvidia-smi, python scripts/executar_projeto.py).
Seja direto, prestativo e conciso. Responda em português (ou no idioma que o usuário falar)."""


def get_provider_details(provider: str, custom_base_url: Optional[str] = None, custom_api_key: Optional[str] = None):
    """Retorna (endpoint_url, headers, is_anthropic)."""
    p = (provider or "ollama").lower()

    if p == "anthropic":
        key = custom_api_key or os.getenv("ANTHROPIC_API_KEY", "")
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        return url, headers, True

    elif p == "gemini":
        key = custom_api_key or os.getenv("GEMINI_API_KEY", "")
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json"
        }
        return url, headers, False

    elif p == "openai":
        key = custom_api_key or os.getenv("OPENAI_API_KEY", "")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json"
        }
        return url, headers, False

    elif p == "groq":
        key = custom_api_key or os.getenv("GROQ_API_KEY", "")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json"
        }
        return url, headers, False

    elif p == "openrouter":
        key = custom_api_key or os.getenv("OPENROUTER_API_KEY", "")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json",
            "HTTP-Referer": "http://localhost:8765",
            "X-Title": "Agent-Remote"
        }
        return url, headers, False

    else:  # ollama ou custom
        base = custom_base_url or "http://127.0.0.1:11434/v1"
        if not base.endswith("/chat/completions"):
            base = base.rstrip("/") + "/chat/completions"
        key = custom_api_key or os.getenv("LLM_API_KEY", "ollama")
        headers = {
            "Authorization": f"Bearer {key}",
            "content-type": "application/json"
        }
        return base, headers, False


async def stream_chat_response(
    messages: List[Dict[str, str]],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.4,
    system_prompt: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Envia mensagens para qualquer provedor (Ollama, OpenAI, Gemini, Claude, Groq, OpenRouter)
    e faz o streaming token a token da resposta.
    """
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})

    chosen_provider = provider or llm_cfg.get("provider", "ollama")
    chosen_model = model or llm_cfg.get("model", "qwen3.5:9b")
    chosen_key = api_key or llm_cfg.get("api_key", "")
    chosen_base = base_url or llm_cfg.get("base_url", "http://127.0.0.1:11434/v1")
    chosen_temp = temperature if temperature is not None else llm_cfg.get("temperature", 0.4)

    url, headers, is_anthropic = get_provider_details(chosen_provider, chosen_base, chosen_key)

    # Preparar mensagens
    full_messages = []
    sys_content = system_prompt or DEFAULT_SYSTEM_PROMPT

    if is_anthropic:
        # Anthropic separa o system prompt das messages
        user_messages = [m for m in messages if m.get("role") != "system"]
        payload = {
            "model": chosen_model,
            "system": sys_content,
            "messages": user_messages,
            "max_tokens": 4096,
            "temperature": chosen_temp,
            "stream": True
        }
    else:
        # Padrão OpenAI
        if not any(m.get("role") == "system" for m in messages):
            full_messages.append({"role": "system", "content": sys_content})
        full_messages.extend(messages)
        payload = {
            "model": chosen_model,
            "messages": full_messages,
            "temperature": chosen_temp,
            "stream": True
        }

    timeout = httpx.Timeout(60.0, connect=10.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    yield f"❌ Erro na API do LLM ({response.status_code}): {err_body.decode('utf-8', errors='replace')}"
                    return

                async for line in response.aiter_lines():
                    if not line or not line.strip():
                        continue

                    # Server-Sent Events parsing
                    clean_line = line.strip()
                    if clean_line.startswith("data: "):
                        data_str = clean_line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            if is_anthropic:
                                # Anthropic SSE: content_block_delta
                                if chunk.get("type") == "content_block_delta":
                                    delta = chunk.get("delta", {})
                                    if delta.get("type") == "text_delta":
                                        yield delta.get("text", "")
                            else:
                                # OpenAI SSE: choices[0].delta.content
                                choices = chunk.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content")
                                    if content:
                                        yield content
                        except json.JSONDecodeError:
                            continue
    except httpx.ConnectError:
        yield f"❌ Não foi possível conectar ao provedor '{chosen_provider}' em {url}. Certifique-se de que o serviço está aberto."
    except Exception as e:
        yield f"❌ Erro inesperado no chat: {str(e)}"
