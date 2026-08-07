import time

import pytest

from agent.guardrails import (
    CallSignatureTracker,
    LoopDetected,
    ToolTimeoutError,
    run_with_timeout,
)


def test_call_signature_tracker_permite_chamadas_distintas():
    tracker = CallSignatureTracker()
    tracker.check_and_record("buscar_arquivo", {"diretorio": "a", "padrao": "*.py"})
    tracker.check_and_record("buscar_arquivo", {"diretorio": "b", "padrao": "*.py"})  # não levanta


def test_call_signature_tracker_detecta_repeticao_exata():
    tracker = CallSignatureTracker()
    args = {"diretorio": "a", "padrao": "*.py"}
    tracker.check_and_record("buscar_arquivo", args)
    with pytest.raises(LoopDetected):
        tracker.check_and_record("buscar_arquivo", dict(args))  # mesmo conteúdo, dict novo


def test_call_signature_tracker_ignora_ordem_das_chaves():
    tracker = CallSignatureTracker()
    tracker.check_and_record("calcular", {"a": 1, "b": 2})
    with pytest.raises(LoopDetected):
        tracker.check_and_record("calcular", {"b": 2, "a": 1})


def test_run_with_timeout_retorna_resultado_normal():
    assert run_with_timeout(lambda x: x * 2, {"x": 21}, timeout_s=1.0) == 42


def test_run_with_timeout_estoura_em_funcao_lenta():
    def lenta():
        time.sleep(0.5)
        return "nunca chega aqui a tempo"

    with pytest.raises(ToolTimeoutError):
        run_with_timeout(lenta, {}, timeout_s=0.05)
