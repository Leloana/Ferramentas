"""CLI mínima: `python -m agent.cli "sua pergunta"` ou modo interativo."""
from __future__ import annotations

import sys

from agent.config import DEFAULT_CONFIG
from agent.llm_client import OllamaLLMClient
from agent.loop import run_agent
from agent.tools import build_default_registry


def main() -> None:
    config = DEFAULT_CONFIG
    registry = build_default_registry(config)
    client = OllamaLLMClient(config)

    print(f"[local-agent] modelo={config.model} max_iters={config.max_iters} "
          f"ferramentas={registry.names()}")
    print(f"[local-agent] diretórios permitidos={[str(d) for d in config.allowed_dirs]}")

    if len(sys.argv) > 1:
        pergunta = " ".join(sys.argv[1:])
        result = run_agent(pergunta, registry=registry, client=client, config=config)
        print(f"\n[{result.status}] ({result.iterations} iterações)\n{result.content}")
        return

    print("Modo interativo. Ctrl+C ou 'sair' para encerrar.\n")
    while True:
        try:
            pergunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pergunta or pergunta.lower() in {"sair", "exit", "quit"}:
            break
        result = run_agent(pergunta, registry=registry, client=client, config=config)
        print(f"[{result.status}] ({result.iterations} iterações)\n{result.content}\n")


if __name__ == "__main__":
    main()
