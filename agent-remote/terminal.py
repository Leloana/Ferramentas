import asyncio
import os
import re
import shlex
from pathlib import Path
from typing import AsyncGenerator, List, Tuple
from config import load_config

# Operadores expressamente proibidos para evitar injeção e encadeamento
FORBIDDEN_OPERATORS = [";", "&&", "||", "|", ">", ">>", "<", "`", "$(", "${"]
# Palavras-chave perigosas que nunca devem ser executadas
FORBIDDEN_KEYWORDS = ["rm", "del", "format", "sudo", "runas", "mkfs", "dd", "shutdown", "reboot"]

REPO_ROOT = Path(__file__).resolve().parent.parent


def validate_command(command_str: str) -> Tuple[bool, str, List[str]]:
    """
    Valida o comando contra a whitelist e operadores proibidos.
    Retorna (is_valid, error_msg, tokens_limpos).
    """
    cmd = command_str.strip()
    if not cmd:
        return False, "Comando vazio", []

    # 1. Verifica operadores proibidos
    for op in FORBIDDEN_OPERATORS:
        if op in cmd:
            return False, f"Operador proibido detectado: '{op}' (pipes e encadeamentos são bloqueados por segurança)", []

    # 2. Tokenização segura com shlex
    try:
        tokens = shlex.split(cmd)
    except Exception as e:
        return False, f"Erro ao analisar comando: {str(e)}", []

    if not tokens:
        return False, "Nenhum token encontrado", []

    base_cmd = tokens[0].lower()

    # Normalizar nome no Windows/Linux (ex: python.exe -> python, git.exe -> git)
    base_cmd_clean = os.path.splitext(os.path.basename(base_cmd))[0].lower()

    # 3. Verifica palavras-chave proibidas
    for kw in FORBIDDEN_KEYWORDS:
        if base_cmd_clean == kw:
            return False, f"Comando '{kw}' é expressamente proibido pela política de segurança.", []

    # 4. Verifica whitelist
    cfg = load_config()
    allowed = [c.lower() for c in cfg.get("terminal", {}).get("allowed_commands", [])]

    if base_cmd_clean not in allowed and base_cmd not in allowed:
        return False, f"Comando '{tokens[0]}' não está na whitelist de comandos permitidos ({', '.join(allowed)}).", []

    return True, "", tokens


async def execute_whitelisted_command(
    command_str: str,
    cwd: str = None
) -> AsyncGenerator[str, None]:
    """
    Executa um comando validado e faz streaming da saída (stdout/stderr) em tempo real.
    """
    is_valid, err_msg, tokens = validate_command(command_str)
    if not is_valid:
        yield f"[ERRO DE SEGURANÇA] {err_msg}\n"
        return

    work_dir = cwd or str(REPO_ROOT)
    yield f"[EXEC] $ {' '.join(tokens)} (em {work_dir})\n"

    try:
        process = await asyncio.create_subprocess_exec(
            *tokens,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=work_dir
        )

        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

        return_code = await process.wait()
        if return_code == 0:
            yield f"\n[SUCESSO] Comando finalizado com código {return_code}.\n"
        else:
            yield f"\n[FALHA] Comando finalizado com erro (código {return_code}).\n"

    except FileNotFoundError:
        yield f"[ERRO] Executável '{tokens[0]}' não foi encontrado no sistema.\n"
    except Exception as e:
        yield f"[ERRO] Falha na execução: {str(e)}\n"
