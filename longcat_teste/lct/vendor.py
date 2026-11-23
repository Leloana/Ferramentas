"""Acesso ao código oficial do LongCat-Video.

O repositório oficial não é um pacote instalável, então ele é clonado em
``longcat_teste/vendor/LongCat-Video`` (commit fixo em ``lct.COMMIT_LONGCAT``)
e entra no ``sys.path``. Outra pasta pode ser apontada com a variável
``LONGCAT_REPO``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VENDOR_PADRAO = RAIZ / "vendor" / "LongCat-Video"


def pasta_repo() -> Path:
    return Path(os.environ.get("LONGCAT_REPO", VENDOR_PADRAO)).resolve()


def garantir_no_path() -> Path:
    """Coloca o repo oficial no sys.path. Erro claro se não foi clonado."""
    repo = pasta_repo()
    if not (repo / "longcat_video" / "pipeline_longcat_video.py").exists():
        raise SystemExit(
            f"Código do LongCat-Video não encontrado em {repo}.\n"
            "Rode:  python preparar.py clonar   (ou defina LONGCAT_REPO)"
        )
    s = str(repo)
    if s not in sys.path:
        sys.path.insert(0, s)
    return repo
