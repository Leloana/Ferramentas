"""Linha do tempo do áudio dos microfones, ancorada no tempo da música.

O celular não toca a música, então não sabe o tempo dela. Cada pacote traz o
índice da primeira amostra (contador contínuo do AudioWorklet) e o servidor
converte índice → tempo da música com uma âncora por jogador:

    tempo(amostra n) = âncora + n / taxa

A âncora é estimada no recebimento de cada pacote pelo tempo da música naquele
instante menos a duração já capturada. Latência de rede só atrasa o
recebimento, então o MENOR valor observado é o mais próximo do real — o filtro
de mínimo descarta o jitter do Wi-Fi/túnel.
"""
from __future__ import annotations

import math
import struct
import time

import numpy as np

STREAM_SR = 16000

# Pacote binário do microfone: magic (4s) + índice da 1ª amostra (float64) +
# taxa (uint32), little-endian, seguido de PCM Int16 mono.
PACKET_MAGIC = b"KM01"
PACKET_HEADER = struct.Struct("<4sdI")

# Diferença entre o tempo informado pela TV e o extrapolado acima disso é seek.
# Folgado de propósito: rajada de mensagens atrasadas pelo túnel não é seek.
CLOCK_JUMP_SEC = 0.75
# Pausa congela o currentTime da TV: avanço abaixo disso após o intervalo
# mínimo é música parada. Pacotes nesse estado são descartados.
CLOCK_STALL_ADVANCE_SEC = 0.02
CLOCK_STALL_MIN_ELAPSED_SEC = 0.15
# Sem atualização da TV, a extrapolação para aqui (TV caiu ou pausou).
CLOCK_MAX_EXTRAPOLATION_SEC = 0.5

# Pacote chegando mais que isso depois do que a âncora prevê: o contador de
# amostras do celular parou ou recomeçou, e a âncora antiga não vale mais.
COUNTER_GAP_SEC = 0.5

# Por quanto tempo após a música parar ainda chegam pacotes gravados antes.
IN_FLIGHT_SEC = 0.5

# Decaimento por pacote (100 ms) do maior atraso recente: meia-vida de ~3,5 s.
LATENESS_DECAY = 0.98

# Relógio do servidor; indireção para os testes controlarem o tempo.
_monotonic = time.monotonic


def parse_packet(data: bytes) -> tuple[float, int, np.ndarray] | None:
    """Devolve (índice da 1ª amostra, taxa, amostras Int16) ou None se inválido."""
    if len(data) <= PACKET_HEADER.size:
        return None
    magic, first_index, sample_rate = PACKET_HEADER.unpack_from(data)
    payload = len(data) - PACKET_HEADER.size
    if magic != PACKET_MAGIC or sample_rate <= 0 or payload % 2:
        return None
    # NaN/infinito viraria âncora NaN e o int(round()) do extract derrubaria a TV
    if not math.isfinite(first_index) or first_index < 0:
        return None
    samples = np.frombuffer(data, dtype="<i2", offset=PACKET_HEADER.size)
    return first_index, sample_rate, samples


def build_packet(first_index: float, samples: np.ndarray, sample_rate: int = STREAM_SR) -> bytes:
    """Monta o pacote no mesmo formato do AudioWorklet (usado nos testes)."""
    pcm = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    return PACKET_HEADER.pack(PACKET_MAGIC, float(first_index), sample_rate) + pcm.tobytes()


class SongClock:
    """Tempo da música no servidor, extrapolado entre os playback_time da TV.

    `epoch` muda a cada descontinuidade (seek, pausa, retomada): amostras de
    épocas diferentes não compartilham âncora.
    """

    def __init__(self) -> None:
        self.song_time = 0.0
        self.received_at: float | None = None
        # Último recebimento em que o tempo da música de fato andou.
        self.advanced_at = 0.0
        self.stalled = True
        self.ended = False
        self.epoch = 0

    def update(self, song_time: float, now: float | None = None) -> None:
        now = _monotonic() if now is None else now
        if self.received_at is None:
            self.epoch += 1
            self.stalled = False
            self.advanced_at = now
        elif abs(song_time - self.song_time) >= CLOCK_STALL_ADVANCE_SEC:
            predicted = self.song_time + (0.0 if self.stalled else now - self.received_at)
            if self.stalled or abs(song_time - predicted) > CLOCK_JUMP_SEC:
                self.epoch += 1
            self.stalled = False
            self.advanced_at = now
        elif not self.stalled and now - self.advanced_at >= CLOCK_STALL_MIN_ELAPSED_SEC:
            self.stalled = True
            self.epoch += 1
        self.song_time = song_time
        self.received_at = now

    def now(self, now: float | None = None) -> float | None:
        """Tempo atual da música, ou None se ela não está tocando."""
        if self.received_at is None or self.stalled:
            return None
        now = _monotonic() if now is None else now
        return self.song_time + min(now - self.received_at, CLOCK_MAX_EXTRAPOLATION_SEC)

    def stop(self) -> None:
        """Fim da música (audio_ended): congela o tempo em vez de extrapolar."""
        self.stalled = True
        self.ended = True

    def just_stopped(self, now: float | None = None) -> bool:
        """Música parou há pouco: pacotes chegando agora foram gravados antes da parada."""
        if self.ended:
            return True
        if not self.stalled or self.received_at is None:
            return False
        now = _monotonic() if now is None else now
        return now - self.advanced_at <= IN_FLIGHT_SEC


class MicTimeline:
    """Áudio contínuo de um jogador, indexado pelo tempo da música."""

    def __init__(self, sample_rate: int = STREAM_SR) -> None:
        self.sample_rate = sample_rate
        # Uma âncora por trecho em que o contador do celular e a música andaram
        # juntos. Trecho novo a cada época do SongClock ou parada do contador.
        self.anchors: dict[int, float] = {}
        self._span = 0
        self._span_epoch: int | None = None
        # Estimativa do pacote que abriu o trecho atual por "contador parado".
        self._gap_opened_at: float | None = None
        # (trecho, índice da 1ª amostra, amostras Int16) em ordem de chegada.
        self.chunks: list[tuple[int, float, np.ndarray]] = []
        # Maior atraso recente de chegada em relação à âncora (segundos).
        self.lateness = 0.0

    def add(self, first_index: float, samples: np.ndarray, song_time: float, epoch: int) -> None:
        """Registra um pacote recebido quando a música estava em `song_time`."""
        if len(samples) == 0:
            return
        estimate = song_time - (first_index + len(samples)) / self.sample_rate
        # Atraso de rede só puxa a estimativa para DEPOIS da âncora, e pouco.
        # Muito depois = o contador parou (tela bloqueada, ligação no iPhone)
        # ou recomeçou do zero (AudioContext recriado).
        stale = self._span in self.anchors and estimate > self.anchors[self._span] + COUNTER_GAP_SEC
        if epoch != self._span_epoch:
            self._span += 1
            self._span_epoch = epoch
            self._gap_opened_at = None
        elif stale:
            self._span += 1
            self._gap_opened_at = estimate
        self.anchors[self._span] = min(self.anchors.get(self._span, estimate), estimate)
        lateness = estimate - self.anchors[self._span]

        # Trecho aberto por "contador parado" cuja âncora voltou para perto da
        # anterior: era só uma rajada de rede lenta. Junta os dois e registra o
        # atraso daquele pacote, que é o que a folga do servidor precisa cobrir.
        prev = self._span - 1
        if self._gap_opened_at is not None and self.anchors[self._span] <= self.anchors[prev] + COUNTER_GAP_SEC:
            merged = min(self.anchors[prev], self.anchors[self._span])
            self.anchors[prev] = self.anchors[self._span] = merged
            lateness = max(lateness, self._gap_opened_at - merged)
            self._gap_opened_at = None

        self.lateness = max(lateness, self.lateness * LATENESS_DECAY)
        self.chunks.append((self._span, first_index, samples))

    def add_in_flight(self, first_index: float, samples: np.ndarray) -> None:
        """Pacote que chegou logo depois de a música parar: usa a âncora atual, sem mexer nela."""
        if len(samples) and self._span in self.anchors:
            self.chunks.append((self._span, first_index, samples))

    def _chunk_span(self, span: int, first_index: float, samples: np.ndarray) -> tuple[float, float]:
        start = self.anchors[span] + first_index / self.sample_rate
        return start, start + len(samples) / self.sample_rate

    def extract(self, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray]:
        """Áudio float32 de [t0, t1) e a máscara das amostras realmente recebidas.

        Trecho sem pacote vira silêncio. Onde dois trechos cobrem o mesmo
        instante (cantou de novo após seek para trás), vence o mais recente.
        """
        n_out = max(0, int(round((t1 - t0) * self.sample_rate)))
        audio = np.zeros(n_out, dtype=np.float32)
        covered = np.zeros(n_out, dtype=bool)
        for span, first_index, samples in self.chunks:
            start, _ = self._chunk_span(span, first_index, samples)
            dst = int(round((start - t0) * self.sample_rate))
            src_lo = max(0, -dst)
            src_hi = min(len(samples), n_out - dst)
            if src_hi <= src_lo:
                continue
            audio[dst + src_lo:dst + src_hi] = samples[src_lo:src_hi] / 32768.0
            covered[dst + src_lo:dst + src_hi] = True
        return audio, covered

    def end_time(self) -> float | None:
        """Tempo da música em que termina o pacote mais tardio (None sem pacotes)."""
        if not self.chunks:
            return None
        return max(self._chunk_span(*c)[1] for c in self.chunks)

    def prune_before(self, t: float) -> None:
        """Descarta pacotes que terminam antes de `t`."""
        self.chunks = [c for c in self.chunks if self._chunk_span(*c)[1] > t]

    def drop_from(self, t: float) -> None:
        """Descarta pacotes que começam em `t` ou depois (seek para trás)."""
        self.chunks = [c for c in self.chunks if self._chunk_span(*c)[0] < t]


def segment_window(segments: list[dict], idx: int, pre_sec: float, post_sec: float) -> tuple[float, float]:
    """Janela de captura [t0, t1) do verso `idx`, disjunta das vizinhas.

    Antes o pré-roll de um verso incluía o fim do anterior e o mesmo áudio era
    pontuado duas vezes (o "vazamento do verso anterior").
    """

    def end_of(i: int) -> float:
        seg = segments[i]
        t1 = seg["sing_end"] + post_sec
        if i + 1 < len(segments):
            t1 = min(t1, max(seg["sing_end"], segments[i + 1]["sing_start"]))
        return t1

    t0 = max(0.0, segments[idx]["sing_start"] - pre_sec)
    if idx > 0:
        t0 = max(t0, end_of(idx - 1))
    return t0, end_of(idx)
