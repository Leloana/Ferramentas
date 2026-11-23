"""Orquestra um vídeo longo: texto -> estágio 1 (480p, 15 fps) -> refino opcional -> pós.

Pasta de saída (tudo retomável; rodar de novo o mesmo comando continua de onde parou):

    estado.json          progresso + assinatura das opções
    quadros/NNN.npy      quadros novos de cada segmento do estágio 1 (uint8)
    segmentos/NNN.mp4    os mesmos quadros em mp4 (para assistir durante a geração)
    cond.npy             13 últimos quadros (condição do próximo segmento)
    refino/NNN.mp4       saída do refino por segmento (se --refino)
    bruto.mp4            concatenação sem pós
    final.mp4            cortado na duração, interpolado e escalado
    medicoes.jsonl       tempo, VRAM e RAM por etapa
"""

from __future__ import annotations

import gc
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from . import FPS_BASE, QUADROS_COND, QUADROS_SEGMENTO, memoria, patches, texto, video_io
from .carregar import carregar_dit_int8, montar_pipeline
from .offload import OffloadPorBloco, blocos_que_cabem, bytes_do_modulo
from .plano import Plano, Roteiro, tamanho_estagio1

GIB = 2**30

MODOS = {
    # variante INT8, passos, cfg, use_distill, enhance_hf (só no vc)
    "distill": {"variante": "dit_distill", "passos": 16, "cfg": 1.0, "use_distill": True, "enhance_hf": False},
    "completo": {"variante": "dit_base", "passos": 50, "cfg": 4.0, "use_distill": False, "enhance_hf": True},
}

# Reserva de VRAM para ativações, por etapa. Chute inicial (não medido):
# calibrar com teste_gpu.py e passar --reserva-gib.
RESERVA_GIB = {"distill": 4.5, "completo": 7.0, "refino": 8.0}


@dataclass
class Opcoes:
    pesos: Path
    int8: Path
    saida: Path
    roteiro: Roteiro
    duracao_s: float = 90.0
    formato: str = "vertical"
    imagem: Optional[Path] = None
    modo: str = "distill"
    passos: Optional[int] = None
    cfg: Optional[float] = None
    seed: int = 42
    quadros: int = QUADROS_SEGMENTO
    blocos_na_gpu: str = "auto"
    reserva_gib: Optional[float] = None
    pin: bool = True
    atencao: str = "auto"
    ffn_tokens: int = 16384
    texto_modo: str = "int8-gpu"
    kv_cache_cpu: bool = True
    vae_tiling: bool = False
    refino: str = "nenhum"          # nenhum | espacial | completo
    refino_bsa: bool = True
    refino_passos: int = 50
    tamanho_final: str = "720x1280"
    fps_final: int = 30
    interp: str = "minterpolate"
    max_segmentos: Optional[int] = None
    recomecar: bool = False

    def assinatura(self) -> str:
        """O que muda o conteúdo do estágio 1. Se mudar, não dá para retomar."""
        d = {
            "trechos": self.roteiro.trechos, "negativo": self.roteiro.negativo, "formato": self.formato,
            "imagem": str(self.imagem) if self.imagem else None, "modo": self.modo, "passos": self.passos,
            "cfg": self.cfg, "seed": self.seed, "quadros": self.quadros,
        }
        return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _limpar():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _pil(quadros: np.ndarray):
    from PIL import Image

    return [Image.fromarray(q) for q in quadros]


def _redimensionar(quadros: np.ndarray, h: int, w: int) -> np.ndarray:
    if quadros.shape[1:3] == (h, w):
        return quadros
    from PIL import Image

    return np.stack([np.asarray(Image.fromarray(q).resize((w, h), Image.BICUBIC)) for q in quadros])


def preparar_imagem(caminho: Path, h: int, w: int):
    """Recorta no centro para a proporção do bucket e redimensiona (i2v)."""
    from PIL import Image

    img = Image.open(caminho).convert("RGB")
    alvo = w / h
    iw, ih = img.size
    if iw / ih > alvo:
        nw = round(ih * alvo)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = round(iw / alvo)
        img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    return img.resize((w, h), Image.LANCZOS)


class Gerador:
    def __init__(self, op: Opcoes, log=print):
        self.op = op
        self.log = log
        self.saida = Path(op.saida)
        self.saida.mkdir(parents=True, exist_ok=True)
        self.med = self.saida / "medicoes.jsonl"
        self.estado = video_io.Estado(self.saida)
        self.plano = Plano(op.duracao_s, FPS_BASE, op.quadros, QUADROS_COND)
        self.cfg_modo = dict(MODOS[op.modo])
        if op.passos:
            self.cfg_modo["passos"] = op.passos
        if op.cfg is not None:
            self.cfg_modo["cfg"] = op.cfg
        self.pipe = None
        self.offload = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    # ------------------------------------------------------------------ #
    def _conferir_assinatura(self):
        ass = self.op.assinatura()
        antiga = self.estado.get("assinatura")
        if self.op.recomecar:
            self.estado.d = {}
        elif antiga and antiga != ass:
            raise SystemExit(
                f"{self.saida} tem uma geração com outras opções (prompt/seed/modo...). "
                "Use outra --saida ou --recomecar para refazer do zero.")
        self.estado.set(assinatura=ass, opcoes={k: str(v) for k, v in asdict(self.op).items() if k != "roteiro"},
                        trechos=self.op.roteiro.trechos)

    def _textos(self, com_refino: bool):
        ts = list(self.op.roteiro.prompts())
        if self.cfg_modo["cfg"] > 1.0:
            ts.append(self.op.roteiro.negativo)
        if com_refino:
            ts.append("")
        return ts

    def _blocos(self, dit, etapa: str) -> int:
        if self.op.blocos_na_gpu != "auto":
            return int(self.op.blocos_na_gpu)
        if not torch.cuda.is_available():
            return 0
        livre, _ = torch.cuda.mem_get_info()
        fora = sum(bytes_do_modulo(m) for n, m in dit.named_children() if n != "blocks")
        reserva = (self.op.reserva_gib or RESERVA_GIB[etapa]) * GIB
        k = blocos_que_cabem(livre - fora, bytes_do_modulo(dit.blocks[0]), int(reserva))
        self.log(f"auto: {livre / GIB:.1f} GiB livres, reserva {reserva / GIB:.1f} GiB -> {k} blocos fixos")
        return k

    def _carregar(self, variante: str, etapa: str, embeddings):
        t0 = time.time()
        atencao = patches.escolher_atencao(self.op.atencao)
        patches.aplicar_tudo(self.op.ffn_tokens)
        pasta = Path(self.op.int8) / variante
        if not (pasta / "quantizacao.json").exists():
            raise SystemExit(f"{pasta} não existe. Rode: python preparar.py quantizar --variante {variante.removeprefix('dit_')}")
        self.log(f"carregando {pasta} ...")
        dit = carregar_dit_int8(pasta, atencao, log=self.log)
        if self.pipe is None:
            self.pipe = montar_pipeline(Path(self.op.pesos), dit, embeddings, device=self.device,
                                         vae_tiling=self.op.vae_tiling)
        else:
            self.pipe.dit = dit
            self.pipe.encode_prompt.embeddings.update(embeddings)
        k = self._blocos(dit, etapa)
        self.offload = OffloadPorBloco(dit, self.device, k, pin=self.op.pin, log=self.log)
        memoria.registrar(self.med, etapa=f"carregar_{variante}", segundos=round(time.time() - t0, 1),
                          blocos_na_gpu=k, atencao=atencao)

    def _descarregar_dit(self):
        if self.offload:
            self.offload.remover()
        self.offload = None
        if self.pipe is not None:
            self.pipe.dit = None
        _limpar()

    # ------------------------------------------------------------------ #
    def estagio1(self):
        op, pl, cm = self.op, self.plano, self.cfg_modo
        feitos = int(self.estado.get("estagio1_feitos", 0))
        total = pl.n_segmentos if op.max_segmentos is None else min(pl.n_segmentos, op.max_segmentos)
        self.log(pl.resumo())
        if feitos >= total:
            self.log("estágio 1 já concluído")
            return total
        h, w = tamanho_estagio1(op.formato)
        neg = op.roteiro.negativo if cm["cfg"] > 1.0 else None

        for seg in range(feitos, total):
            prompt = op.roteiro.prompt_em(pl.inicio_s(seg))
            gen = torch.Generator(device=self.device).manual_seed(op.seed + seg)
            memoria.zerar_pico()
            t0 = time.time()
            self.log(f"segmento {seg + 1}/{total} ({pl.inicio_s(seg):.1f}s): {prompt[:70]!r}")
            comum = dict(prompt=prompt, negative_prompt=neg, num_frames=op.quadros,
                         num_inference_steps=cm["passos"], use_distill=cm["use_distill"],
                         guidance_scale=cm["cfg"], generator=gen)
            if seg == 0 and op.imagem:
                saida = self.pipe.generate_i2v(image=preparar_imagem(op.imagem, h, w), resolution="480p", **comum)[0]
            elif seg == 0:
                saida = self.pipe.generate_t2v(height=h, width=w, **comum)[0]
            else:
                cond = np.load(self.saida / "cond.npy")
                saida = self.pipe.generate_vc(video=_pil(cond), resolution="480p", num_cond_frames=QUADROS_COND,
                                              use_kv_cache=True, offload_kv_cache=op.kv_cache_cpu,
                                              enhance_hf=cm["enhance_hf"], **comum)[0]
            quadros = _redimensionar(video_io.para_uint8(saida), h, w)
            del saida
            novos = quadros if seg == 0 else quadros[QUADROS_COND:]
            video_io.salvar_npy(novos, self.saida / "quadros" / f"{seg:03d}.npy")
            video_io.gravar_mp4(novos, self.saida / "segmentos" / f"{seg:03d}.mp4", FPS_BASE)
            video_io.salvar_npy(quadros[-QUADROS_COND:], self.saida / "cond.npy")
            self.estado.set(estagio1_feitos=seg + 1)
            dt = time.time() - t0
            memoria.registrar(self.med, etapa="estagio1", segmento=seg, segundos=round(dt, 1),
                              quadros_novos=len(novos), passos=cm["passos"])
            self.log(f"  ok em {dt / 60:.1f} min")
            _limpar()
        return total

    def refino(self, n_seg: int):
        op = self.op
        espacial = op.refino == "espacial"
        n_cond = QUADROS_COND if espacial else 2 * QUADROS_COND
        fps = FPS_BASE if espacial else 2 * FPS_BASE
        feitos = int(self.estado.get("refino_feitos", 0))
        if feitos >= n_seg:
            self.log("refino já concluído")
            return fps
        if op.refino_bsa:
            self.pipe.dit.enable_bsa()
        arquivos = [self.saida / "quadros" / f"{i:03d}.npy" for i in range(n_seg)]
        est1 = video_io.QuadrosEstagio1(arquivos)
        passo = op.quadros - QUADROS_COND
        for seg in range(feitos, n_seg):
            ini = seg * passo
            bloco = est1.intervalo(ini, ini + op.quadros)
            cond = None if seg == 0 else _pil(np.load(self.saida / "refino_cond.npy"))
            gen = torch.Generator(device=self.device).manual_seed(op.seed + 1000 + seg)
            memoria.zerar_pico()
            t0 = time.time()
            self.log(f"refino {seg + 1}/{n_seg}")
            saida = self.pipe.generate_refine(video=cond, prompt="", stage1_video=_pil(bloco),
                                              num_cond_frames=0 if seg == 0 else n_cond,
                                              num_inference_steps=op.refino_passos, generator=gen,
                                              spatial_refine_only=espacial)[0]
            quadros = video_io.para_uint8(saida)
            del saida
            novos = quadros if seg == 0 else quadros[n_cond:]
            video_io.gravar_mp4(novos, self.saida / "refino" / f"{seg:03d}.mp4", fps)
            video_io.salvar_npy(quadros[-n_cond:], self.saida / "refino_cond.npy")
            self.estado.set(refino_feitos=seg + 1, refino_modo=op.refino)
            dt = time.time() - t0
            memoria.registrar(self.med, etapa=f"refino_{op.refino}", segmento=seg, segundos=round(dt, 1),
                              resolucao=f"{quadros.shape[2]}x{quadros.shape[1]}")
            self.log(f"  ok em {dt / 60:.1f} min ({quadros.shape[2]}x{quadros.shape[1]})")
            _limpar()
        return fps

    def finalizar(self, n_seg: int, refinado: bool, fps_bruto: int):
        pasta = self.saida / ("refino" if refinado else "segmentos")
        partes = [pasta / f"{i:03d}.mp4" for i in range(n_seg)]
        bruto = self.saida / "bruto.mp4"
        video_io.concatenar(partes, bruto)
        final = self.saida / "final.mp4"
        interp = self.op.interp if fps_bruto < self.op.fps_final else "nenhum"
        video_io.pos_processar(bruto, final, self.op.duracao_s, self.op.fps_final, self.op.tamanho_final, interp)
        self.log(f"pronto: {final}")
        return final

    # ------------------------------------------------------------------ #
    def rodar(self):
        op = self.op
        self._conferir_assinatura()
        com_refino = op.refino != "nenhum"
        t0 = time.time()
        emb = texto.codificar(Path(op.pesos), self._textos(com_refino), Path(op.int8).parent / "cache_texto",
                              op.texto_modo, log=self.log)
        memoria.registrar(self.med, etapa="texto", segundos=round(time.time() - t0, 1))

        total = self.plano.n_segmentos if op.max_segmentos is None else min(self.plano.n_segmentos, op.max_segmentos)
        if int(self.estado.get("estagio1_feitos", 0)) < total:
            self._carregar(self.cfg_modo["variante"], op.modo, emb)
            n_seg = self.estagio1()
        else:
            n_seg = total
        fps = FPS_BASE
        if com_refino:
            if self.estado.get("refino_modo") not in (None, op.refino):
                self.estado.set(refino_feitos=0)
            if int(self.estado.get("refino_feitos", 0)) < n_seg:
                self._descarregar_dit()
                self._carregar("dit_refino", "refino", emb)
            fps = self.refino(n_seg)
        self._descarregar_dit()
        return self.finalizar(n_seg, com_refino, fps)
