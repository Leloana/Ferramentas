"""Conta de segmentos e roteiro de prompts para um vídeo de N segundos.

O LongCat gera 93 quadros por chamada a 15 fps (6,2 s). Cada continuação
recebe os 13 últimos quadros como condição e entrega 80 quadros novos
(5,33 s). Para 90 s: 93 + 16 x 80 = 1373 quadros = 91,5 s, depois corta em 90.

Roteiro (JSON), opcional, para mudar o prompt ao longo do vídeo:

    {
      "negativo": "opcional, substitui o negativo padrão",
      "trechos": [
        {"segundos": 30, "prompt": "..."},
        {"segundos": 30, "prompt": "..."},
        {"prompt": "... vale até o fim"}
      ]
    }

Cada segmento usa o prompt do trecho em que começam os seus quadros novos.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import FPS_BASE, QUADROS_COND, QUADROS_SEGMENTO

NEGATIVO_PADRAO = (
    "Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, images, static, "
    "overall gray, worst quality, low quality, JPEG compression residue, ugly, incomplete, extra fingers, "
    "poorly drawn hands, poorly drawn faces, deformed, disfigured, misshapen limbs, fused fingers, still picture, "
    "messy background, three legs, many people in the background, walking backwards"
)  # o mesmo dos demos oficiais


@dataclass
class Plano:
    duracao_s: float
    fps: int = FPS_BASE
    quadros: int = QUADROS_SEGMENTO
    cond: int = QUADROS_COND

    @property
    def novos_por_continuacao(self) -> int:
        return self.quadros - self.cond

    @property
    def n_continuacoes(self) -> int:
        alvo = math.ceil(self.duracao_s * self.fps)
        if alvo <= self.quadros:
            return 0
        return math.ceil((alvo - self.quadros) / self.novos_por_continuacao)

    @property
    def n_segmentos(self) -> int:
        return 1 + self.n_continuacoes

    @property
    def quadros_totais(self) -> int:
        return self.quadros + self.n_continuacoes * self.novos_por_continuacao

    def inicio_novos(self, seg: int) -> int:
        """Índice do 1º quadro novo do segmento ``seg`` no vídeo final."""
        return 0 if seg == 0 else self.quadros + (seg - 1) * self.novos_por_continuacao

    def inicio_s(self, seg: int) -> float:
        return self.inicio_novos(seg) / self.fps

    def resumo(self) -> str:
        return (f"{self.duracao_s:g}s a {self.fps} fps: {self.n_segmentos} segmentos "
                f"(1 x {self.quadros} + {self.n_continuacoes} x {self.novos_por_continuacao} novos) "
                f"= {self.quadros_totais} quadros ({self.quadros_totais / self.fps:.1f}s antes do corte)")


@dataclass
class Roteiro:
    trechos: List[tuple] = field(default_factory=list)  # (inicio_s, prompt)
    negativo: str = NEGATIVO_PADRAO

    def prompt_em(self, t: float) -> str:
        atual = self.trechos[0][1]
        for ini, p in self.trechos:
            if t + 1e-9 >= ini:
                atual = p
        return atual

    def prompts(self) -> List[str]:
        return list(dict.fromkeys(p for _, p in self.trechos))


def roteiro_de_prompt(prompt: str, negativo: Optional[str] = None) -> Roteiro:
    return Roteiro([(0.0, prompt)], negativo or NEGATIVO_PADRAO)


def ler_roteiro(caminho: Path, negativo: Optional[str] = None) -> Roteiro:
    d = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if isinstance(d, list):
        d = {"trechos": d}
    trechos, t = [], 0.0
    for i, tr in enumerate(d.get("trechos", [])):
        p = (tr.get("prompt") or "").strip()
        if not p:
            raise ValueError(f"roteiro: trecho {i} sem prompt")
        trechos.append((t, p))
        seg = tr.get("segundos")
        if seg is None:
            if i != len(d["trechos"]) - 1:
                raise ValueError(f"roteiro: só o último trecho pode ficar sem 'segundos' (trecho {i})")
        else:
            if float(seg) <= 0:
                raise ValueError(f"roteiro: trecho {i} com segundos <= 0")
            t += float(seg)
    if not trechos:
        raise ValueError("roteiro sem trechos")
    return Roteiro(trechos, negativo or d.get("negativo") or NEGATIVO_PADRAO)


def tamanho_estagio1(formato: str) -> tuple:
    """(altura, largura) do bucket 480p do LongCat."""
    if formato == "vertical":
        return 832, 480
    if formato == "horizontal":
        return 480, 832
    raise ValueError(f"formato desconhecido: {formato}")
