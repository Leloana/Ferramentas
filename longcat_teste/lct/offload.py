"""Offload do DiT por bloco: N blocos fixos na GPU, o resto vem da RAM.

O DiT INT8 tem ~13 GiB (48 blocos de ~270 MiB), mais que os 12 GB da 4070.
Embeddings, camada final e os ``blocos_na_gpu`` primeiros blocos ficam na GPU;
os demais ficam na RAM (pinned, se der) e sobem um de cada vez:

    pre-hook(bloco i):  espera a cópia de i, dispara a cópia do próximo
    post-hook(bloco i): devolve i para a RAM (só troca o ponteiro, o peso não muda)

A cópia roda num stream CUDA separado, então o próximo bloco sobe enquanto o
atual calcula. No máximo 2 blocos "de passagem" ficam na GPU ao mesmo tempo.
Em CPU (testes) tudo vira cópia síncrona e o resultado é o mesmo.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import torch

Slot = Tuple[torch.nn.Module, str, bool]  # (módulo dono, nome, é_parâmetro)


def bytes_do_modulo(m: torch.nn.Module) -> int:
    return sum(t.numel() * t.element_size() for t in list(m.parameters()) + list(m.buffers()))


def _slots(bloco: torch.nn.Module) -> List[Slot]:
    out = []
    for mod in bloco.modules():
        for nome, p in mod._parameters.items():
            if p is not None:
                out.append((mod, nome, True))
        for nome, b in mod._buffers.items():
            if b is not None:
                out.append((mod, nome, False))
    return out


def _ler(slot: Slot) -> torch.Tensor:
    mod, nome, eh_param = slot
    return mod._parameters[nome].data if eh_param else mod._buffers[nome]


def _escrever(slot: Slot, t: torch.Tensor):
    mod, nome, eh_param = slot
    if eh_param:
        mod._parameters[nome].data = t
    else:
        mod._buffers[nome] = t


class OffloadPorBloco:
    def __init__(self, dit, device="cuda", blocos_na_gpu: int = 0, pin: bool = True, log=print):
        self.dit = dit
        self.device = torch.device(device)
        self.log = log
        n = len(dit.blocks)
        self.k = max(0, min(int(blocos_na_gpu), n))
        self.cuda = self.device.type == "cuda"
        self.stream = torch.cuda.Stream(device=self.device) if self.cuda else None

        for nome, filho in dit.named_children():
            if nome != "blocks":
                filho.to(self.device)
        for i in range(self.k):
            dit.blocks[i].to(self.device)

        self.passagem = list(range(self.k, n))
        self.slots: Dict[int, List[Slot]] = {}
        self.na_cpu: Dict[int, List[torch.Tensor]] = {}
        self.eventos: Dict[int, Optional[torch.cuda.Event]] = {}
        self.carregados: Dict[int, List[torch.Tensor]] = {}
        self.buffer: Optional[torch.Tensor] = None
        self.pin_ok = False
        self._empacotar(pin and self.cuda)
        self.handles = []
        for pos, i in enumerate(self.passagem):
            prox = self.passagem[(pos + 1) % len(self.passagem)]
            bloco = dit.blocks[i]
            self.handles.append(bloco.register_forward_pre_hook(self._pre(i, prox)))
            self.handles.append(bloco.register_forward_hook(self._pos(i)))

        b = bytes_do_modulo(dit.blocks[0]) if n else 0
        log(f"offload: {self.k} blocos fixos na GPU, {len(self.passagem)} de passagem "
            f"(~{b / 2**20:.0f} MiB cada, pinned={self.pin_ok})")

    # -- RAM -------------------------------------------------------------- #
    def _empacotar(self, pin: bool):
        """Copia os blocos de passagem para um buffer único na RAM.

        ``tensor.pin_memory()`` usa o alocador do PyTorch, que arredonda cada
        pedaço para potência de 2 (43 MiB viram 64 MiB): ~40% a mais de RAM.
        Aqui é um ``torch.empty`` do tamanho exato, registrado como pinned com
        ``cudaHostRegister``. Bloco a bloco, para o peso original ser liberado
        logo depois de copiado (o pico não dobra).
        """
        for i in self.passagem:
            self.dit.blocks[i].to("cpu")
            self.slots[i] = _slots(self.dit.blocks[i])
        tamanhos = {i: [_alinhar(_ler(s).numel() * _ler(s).element_size()) for s in self.slots[i]]
                    for i in self.passagem}
        total = sum(sum(v) for v in tamanhos.values())
        if total == 0:
            return
        self.buffer = torch.empty(total, dtype=torch.uint8)
        if pin:
            self.pin_ok = _registrar_pinned(self.buffer, self.log)
        pos = 0
        for i in self.passagem:
            cpu = []
            for s, n in zip(self.slots[i], tamanhos[i]):
                t = _ler(s)
                nbytes = t.numel() * t.element_size()
                v = self.buffer[pos:pos + nbytes].view(t.dtype).view(t.shape)
                v.copy_(t)
                _escrever(s, v)  # o tensor original perde a última referência aqui
                cpu.append(v)
                pos += n
            self.na_cpu[i] = cpu

    # -- cópia ------------------------------------------------------------ #
    def _subir(self, i: int):
        if i in self.carregados:
            return
        if self.cuda:
            with torch.cuda.stream(self.stream):
                gpu = [t.to(self.device, non_blocking=self.pin_ok) for t in self.na_cpu[i]]
                ev = torch.cuda.Event()
                ev.record(self.stream)
            self.eventos[i] = ev
        else:
            gpu = [t.to(self.device) for t in self.na_cpu[i]]
            self.eventos[i] = None
        self.carregados[i] = gpu

    def _pre(self, i: int, prox: int):
        def hook(_mod, _args):
            self._subir(i)
            ev = self.eventos.pop(i, None)
            gpu = self.carregados[i]
            if self.cuda:
                atual = torch.cuda.current_stream(self.device)
                if ev is not None:
                    atual.wait_event(ev)
                for t in gpu:
                    t.record_stream(atual)  # o alocador não reaproveita antes do cálculo acabar
            for s, t in zip(self.slots[i], gpu):
                _escrever(s, t)
            if prox != i:
                self._subir(prox)
        return hook

    def _pos(self, i: int):
        def hook(_mod, _args, _out):
            for s, t in zip(self.slots[i], self.na_cpu[i]):
                _escrever(s, t)
            self.carregados.pop(i, None)
        return hook

    def remover(self):
        """Tira os hooks e solta o buffer (o DiT não deve mais ser usado depois disso)."""
        for h in self.handles:
            h.remove()
        self.handles = []
        if self.cuda:
            torch.cuda.synchronize(self.device)
        self.carregados.clear()
        if self.buffer is not None and self.pin_ok:
            torch.cuda.cudart().cudaHostUnregister(self.buffer.data_ptr())
            self.pin_ok = False
        self.na_cpu.clear()
        self.buffer = None


def _alinhar(n: int, a: int = 512) -> int:
    return (n + a - 1) // a * a


def _registrar_pinned(buf: torch.Tensor, log) -> bool:
    try:
        rc = torch.cuda.cudart().cudaHostRegister(buf.data_ptr(), buf.numel(), 0)
        ok = int(rc) == 0 if not hasattr(rc, "value") else rc.value == 0
    except Exception as e:  # noqa: BLE001 - qualquer falha aqui só tira o pinned
        log(f"offload: cudaHostRegister falhou ({e}); seguindo sem pinned (cópia mais lenta)")
        return False
    if not ok:
        log(f"offload: cudaHostRegister devolveu {rc}; seguindo sem pinned (cópia mais lenta)")
    return ok


def blocos_que_cabem(vram_livre: int, bytes_bloco: int, reserva: int, folga_passagem: int = 2) -> int:
    """Quantos blocos fixos cabem: livre - reserva de ativações - 2 blocos de passagem."""
    if bytes_bloco <= 0:
        return 0
    return max(0, (vram_livre - reserva) // bytes_bloco - folga_passagem)
