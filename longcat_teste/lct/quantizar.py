"""Quantização INT8 do DiT do LongCat-Video, em streaming.

Por que não usar ``quantize_model`` do repo oficial: ele precisa do modelo
inteiro carregado em bf16 (13,6B parâmetros = ~27 GB) e, ao instanciar a
classe, aloca tudo em fp32 (~54 GB). Com 32 GB de RAM e pagefile pequeno na
máquina Windows, isso trava o PC. Aqui cada tensor é lido do safetensors,
quantizado e descartado; o pico de RAM fica perto de um shard de saída.

O formato de saída é o mesmo do ``QuantizedLinear`` oficial
(``<modulo>.weight_int8`` int8, ``<modulo>.weight_scale`` fp32, ``<modulo>.bias``
bf16), com quantização simétrica por canal de saída, igual à oficial.

LoRA fundida: o LongCat usa LoRAs para o modo destilado (``cfg_step_lora``,
16 passos sem CFG) e para o refino 720p (``refinement_lora``). Aplicar a LoRA
em tempo de execução custaria ~1,5 GB de VRAM por LoRA (rank 128 em todas as
lineares). Então a LoRA é somada ao peso bf16 *antes* de quantizar:
``W' = W + mult * alpha_scale * up @ down``, gerando uma variante INT8 própria
(ex.: ``int8/dit_distill``).
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

import torch

LORA_PREFIXO = "lora___lorahyphen___"
LORA_HIFEN = "___lorahyphen___"

# Lineares que ficam em bf16: só a projeção final, igual ao DEFAULT_SKIP_PATTERNS
# oficial (assim o resultado é bit a bit o do quantize_model oficial).
PULAR_PADRAO: Tuple[str, ...] = ("final_layer.linear",)

VERSAO_FORMATO = 1


# --------------------------------------------------------------------------- #
# Núcleo numérico (sem dependência do repo oficial, testável isolado)
# --------------------------------------------------------------------------- #

def quantizar_peso(w: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
    """INT8 simétrico por canal de saída. Igual a ``QuantizedLinear.from_linear``."""
    w = w.float()
    escala = w.abs().amax(dim=1).clamp(min=1e-8) / 127.0
    q = (w / escala.unsqueeze(1)).round().clamp(-128, 127).to(torch.int8)
    return q, escala


def desquantizar(q: torch.Tensor, escala: torch.Tensor) -> torch.Tensor:
    return q.float() * escala.float().unsqueeze(1)


def nome_lora(modulo: str) -> str:
    return LORA_PREFIXO + modulo.replace(".", LORA_HIFEN)


def modulo_da_lora(nome: str) -> str:
    return nome.replace(LORA_PREFIXO, "").replace(LORA_HIFEN, ".")


def deltas_da_lora(
    sd: Dict[str, torch.Tensor],
    multiplicador: float = 1.0,
    rank_nominal: int = 128,
    alpha_nominal: float = 64.0,
) -> Dict[str, "DeltaLora"]:
    """Agrupa o state_dict de uma LoRA do LongCat por módulo.

    Reproduz ``LoRAModule``/``LoRANetwork`` do repo oficial: ``alpha_scale`` vem
    do arquivo se existir, senão ``alpha/rank`` com os valores fixos que o
    ``load_lora`` oficial passa (rank 128, alpha 64).
    """
    nomes = {k[: -len(".lora_down.weight")] for k in sd if k.endswith(".lora_down.weight")}
    deltas = {}
    for nome in nomes:
        down = sd[f"{nome}.lora_down.weight"]
        if f"{nome}.lora_up.weight" in sd:
            ups = [sd[f"{nome}.lora_up.weight"]]
        else:
            n = sum(1 for k in sd if k.startswith(f"{nome}.lora_up.blocks."))
            ups = [sd[f"{nome}.lora_up.blocks.{i}.weight"] for i in range(n)]
            if not ups:
                raise ValueError(f"LoRA {nome}: sem lora_up")
        if f"{nome}.alpha_scale" in sd:
            alpha_scale = float(sd[f"{nome}.alpha_scale"].float().item())
        else:
            alpha_scale = alpha_nominal / rank_nominal
        deltas[modulo_da_lora(nome)] = DeltaLora(down, ups, alpha_scale * multiplicador)
    return deltas


class DeltaLora:
    def __init__(self, down: torch.Tensor, ups, escala: float):
        self.down = down
        self.ups = ups
        self.escala = escala

    def matriz(self) -> torch.Tensor:
        """Delta denso [out, in] em fp32."""
        n = len(self.ups)
        down = self.down.float()
        r = down.shape[0] // n
        partes = [up.float() @ down[i * r:(i + 1) * r] for i, up in enumerate(self.ups)]
        return torch.cat(partes, dim=0) * self.escala


# --------------------------------------------------------------------------- #
# Descoberta das lineares (precisa do código oficial)
# --------------------------------------------------------------------------- #

def lineares_do_dit(config: dict) -> Set[str]:
    """Nomes de todos os nn.Linear do DiT, instanciando no device meta (custo zero)."""
    from .carregar import instanciar_dit_meta

    dit = instanciar_dit_meta(config)
    return {n for n, m in dit.named_modules() if isinstance(m, torch.nn.Linear)}


def deve_pular(nome: str, pular: Iterable[str]) -> bool:
    return any(p in nome for p in pular)


# --------------------------------------------------------------------------- #
# Conversão em streaming
# --------------------------------------------------------------------------- #

def _shards_entrada(pasta: Path):
    idx = sorted(pasta.glob("*.safetensors.index.json"))
    if idx:
        mapa = json.loads(idx[0].read_text())["weight_map"]
        return sorted(set(mapa.values()))
    arquivos = sorted(p.name for p in pasta.glob("*.safetensors"))
    if not arquivos:
        raise FileNotFoundError(f"Nenhum .safetensors em {pasta}")
    return arquivos


def quantizar_dit(
    entrada: Path,
    saida: Path,
    lora: Optional[Path] = None,
    multiplicador_lora: float = 1.0,
    pular: Tuple[str, ...] = PULAR_PADRAO,
    lineares: Optional[Set[str]] = None,
    log=print,
) -> dict:
    """Converte ``entrada`` (pasta ``dit`` bf16 do HF) em ``saida`` (INT8).

    ``lineares`` permite injetar a lista nos testes; por padrão vem do modelo
    instanciado no meta a partir de ``entrada/config.json``.
    Retorna o resumo gravado em ``saida/quantizacao.json``.
    """
    from safetensors import safe_open
    from safetensors.torch import save_file

    entrada, saida = Path(entrada), Path(saida)
    config = json.loads((entrada / "config.json").read_text())
    if lineares is None:
        lineares = lineares_do_dit(config)

    deltas = {}
    if lora is not None:
        from safetensors.torch import load_file

        deltas = deltas_da_lora(load_file(str(lora), device="cpu"), multiplicador_lora)
        sem_alvo = sorted(set(deltas) - set(lineares))
        if sem_alvo:
            raise ValueError(f"LoRA tem {len(sem_alvo)} módulos que não são lineares do DiT, ex.: {sem_alvo[:3]}")
        log(f"LoRA {lora.name}: {len(deltas)} módulos serão fundidos")

    tmp = saida.with_name(saida.name + ".parcial")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    shards = _shards_entrada(entrada)
    mapa_saida: Dict[str, str] = {}
    quantizados: Set[str] = set()
    lora_aplicada: Set[str] = set()
    bytes_saida = 0
    t0 = time.time()

    for i, nome_shard in enumerate(shards, 1):
        nome_out = f"dit-int8-{i:05d}-de-{len(shards):05d}.safetensors"
        bloco: Dict[str, torch.Tensor] = {}
        with safe_open(str(entrada / nome_shard), framework="pt", device="cpu") as f:
            for chave in f.keys():
                t = f.get_tensor(chave)
                modulo, _, campo = chave.rpartition(".")
                eh_linear = modulo in lineares
                if eh_linear and campo == "weight":
                    w = t.float()
                    if modulo in deltas:
                        w += deltas[modulo].matriz()
                        lora_aplicada.add(modulo)
                    if deve_pular(modulo, pular):
                        bloco[chave] = w.to(torch.bfloat16)
                    else:
                        q, s = quantizar_peso(w)
                        bloco[f"{modulo}.weight_int8"] = q
                        bloco[f"{modulo}.weight_scale"] = s
                        quantizados.add(modulo)
                    del w
                elif t.is_floating_point():
                    bloco[chave] = t.to(torch.bfloat16)
                else:
                    bloco[chave] = t
        for k, v in bloco.items():
            mapa_saida[k] = nome_out
            bytes_saida += v.numel() * v.element_size()
        save_file(bloco, str(tmp / nome_out))
        del bloco
        log(f"  shard {i}/{len(shards)} ok ({time.time() - t0:.0f}s)")

    faltou = sorted(set(deltas) - lora_aplicada)
    if faltou:
        shutil.rmtree(tmp)
        raise ValueError(f"{len(faltou)} módulos da LoRA não acharam peso, ex.: {faltou[:3]}")

    (tmp / "dit-int8.safetensors.index.json").write_text(
        json.dumps({"metadata": {"total_size": bytes_saida}, "weight_map": mapa_saida}, indent=1)
    )
    shutil.copy2(entrada / "config.json", tmp / "config.json")
    resumo = {
        "versao_formato": VERSAO_FORMATO,
        "metodo": "int8_por_canal_simetrico (igual QuantizedLinear oficial)",
        "quantizados": sorted(quantizados),
        "pular": list(pular),
        "lora": None if lora is None else {"arquivo": lora.name, "multiplicador": multiplicador_lora, "modulos": len(deltas)},
        "bytes": bytes_saida,
        "segundos": round(time.time() - t0, 1),
    }
    (tmp / "quantizacao.json").write_text(json.dumps(resumo, indent=1, ensure_ascii=False))

    if saida.exists():
        shutil.rmtree(saida)
    tmp.rename(saida)
    log(f"INT8 pronto em {saida} ({bytes_saida / 2**30:.1f} GiB, {len(quantizados)} lineares)")
    return resumo
