from __future__ import annotations
import time
from orchestrator.validators import ValidationError_

# Máximo de tentativas por camada
MAX_RETRIES = {
    "A": 3,
    "B": 3,
    "C": 2,
    "D": 2,
    "E": 0,  # nunca retry automático
}


def with_retry(fn, state, agent_name: str, max_retries: int = 3):
    """
    Executa fn() com retry. fn deve lançar ValidationError_ em caso de falha.
    Retorna o resultado de fn() ou lança após esgotar tentativas.
    """
    attempt = 0
    last_error = None

    while attempt <= max_retries:
        try:
            result = fn(attempt=attempt, last_error=last_error)
            if attempt > 0:
                print(f"  [retry] {agent_name} OK na tentativa {attempt + 1}")
            return result
        except ValidationError_ as e:
            last_error = e
            attempt += 1
            retries_key = f"{agent_name}_attempt_{attempt}"
            state.retries[retries_key] = attempt
            print(f"  [retry] {agent_name} falhou ({e}). Tentativa {attempt}/{max_retries}...")
            time.sleep(0.1)  # pequeno backoff

    state.add_error(f"{agent_name}: esgotou {max_retries} tentativas. Último erro: {last_error}")
    raise last_error
