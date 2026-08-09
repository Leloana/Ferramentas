"""Alinhamento forçado por palavra via MMS_FA (torchaudio), rodando sempre em
CPU — decisão explícita (ver tts_platform_pt/CLAUDE.md): a VRAM da GPU já
fica apertada quando o servidor roda junto com o ComfyUI Desktop (medido
~417MB livres numa RTX 4070 de 12GB), então não vale a pena disputar espaço
com o XTTS-v2 por um segundo modelo. Clipes curtos (uma frase por vez, ver
`TTSEngine.synthesize`) alinham rápido o bastante em CPU.

Baseado no núcleo de alinhamento do projeto `karaoke`
(`karaoke/server/utils/lrc_pro.py`), mas bem mais simples: aqui alinhamos UM
clipe curto (uma frase isolada, já sintetizada) contra o texto exato que
gerou esse clipe — não uma letra de música inteira contra vocal com ruído de
fundo —, então não precisamos da lógica de pauta/linha que o karaoke usa pra
exibição em tempo real, só do núcleo MMS_FA.
"""
import logging
import re

import numpy as np
import torch
import torchaudio
from unidecode import unidecode

logger = logging.getLogger("TTSPlatform")

_SAMPLE_RATE_MMS_FA = 16000

# Vocabulário do MMS_FA é romanizado: só a-z e apóstrofo. Mesma normalização
# usada pelo karaoke (`lrc_pro.py:parse_and_normalize_lyrics`) — remove
# acento (unidecode) e qualquer caractere fora desse conjunto.
_NORMALIZAR_RE = re.compile(r"[^a-z']")


def _normalizar(palavra: str) -> str:
    return _NORMALIZAR_RE.sub("", unidecode(palavra).lower())


class ForcedAligner:
    def __init__(self):
        bundle = torchaudio.pipelines.MMS_FA
        self.model = bundle.get_model().to("cpu")
        self.tokenizer = bundle.get_tokenizer()
        self.aligner = bundle.get_aligner()
        logger.info("MMS_FA (alinhador forçado de palavras) carregado em CPU.")

    def align(self, wav: np.ndarray, sample_rate: int, palavras: list[str]) -> list[dict]:
        """Alinha `palavras` (já sem pontuação, ver `_limpar_pontuacao` em
        `scripts/montar_video.py`) contra `wav` (clipe de UMA frase, mono,
        já sem silêncio de borda — ver `_trim_silencio`). Retorna sempre uma
        lista do mesmo tamanho de `palavras`, com timestamps RELATIVOS ao
        início do clipe (quem chama soma o offset absoluto na faixa final).
        Se o MMS_FA falhar por completo (clipe vazio, exceção do modelo,
        nenhuma palavra sobrevive à normalização), cai pra interpolação
        proporcional via `_preencher_faltantes` em vez de propagar o erro —
        a síntese de áudio não pode quebrar por causa deste passo opcional
        de legendagem."""
        if not palavras:
            return []

        duracao_s = len(wav) / sample_rate if sample_rate else 0.0
        if len(wav) == 0:
            return _preencher_faltantes([None] * len(palavras), palavras, 0.0)

        normalizadas = [_normalizar(p) for p in palavras]
        indices_validos = [i for i, n in enumerate(normalizadas) if n]
        if not indices_validos:
            return _preencher_faltantes([None] * len(palavras), palavras, duracao_s)

        waveform = torch.from_numpy(np.asarray(wav)).float().unsqueeze(0)
        if sample_rate != _SAMPLE_RATE_MMS_FA:
            waveform = torchaudio.functional.resample(waveform, sample_rate, _SAMPLE_RATE_MMS_FA)

        try:
            tokens = self.tokenizer([normalizadas[i] for i in indices_validos])
            with torch.inference_mode():
                emission, _ = self.model(waveform)
                spans = self.aligner(emission[0], tokens)
        except Exception as e:
            logger.warning(f"Alinhamento forçado falhou pra esta frase, caindo pra interpolação: {e}")
            return _preencher_faltantes([None] * len(palavras), palavras, duracao_s)

        ratio = duracao_s / emission.size(1)
        resultado: list[dict | None] = [None] * len(palavras)
        for idx_valido, span in zip(indices_validos, spans):
            if not span:
                continue
            resultado[idx_valido] = {
                "texto": palavras[idx_valido],
                "inicio_s": round(span[0].start * ratio, 3),
                "fim_s": round(span[-1].end * ratio, 3),
            }

        return _preencher_faltantes(resultado, palavras, duracao_s)


def _preencher_faltantes(resultado: list[dict | None], palavras: list[str], duracao_total_s: float) -> list[dict]:
    """Palavras sem span do MMS_FA (raro em áudio sintético limpo, sem
    ruído de fundo) recebem timestamp por interpolação proporcional ao nº
    de caracteres, dentro do intervalo entre a palavra alinhada anterior e
    a seguinte (ou entre a borda do clipe e a palavra alinhada mais
    próxima, se a falha for no início/fim)."""
    n = len(palavras)
    i = 0
    while i < n:
        if resultado[i] is not None:
            i += 1
            continue
        j = i
        while j < n and resultado[j] is None:
            j += 1
        inicio = resultado[i - 1]["fim_s"] if i > 0 else 0.0
        fim = resultado[j]["inicio_s"] if j < n else duracao_total_s
        faltantes = palavras[i:j]
        total_chars = sum(len(p) for p in faltantes) or len(faltantes)
        cursor = inicio
        for k, palavra in enumerate(faltantes):
            peso = (len(palavra) / total_chars) if total_chars else (1 / len(faltantes))
            duracao = max(fim - inicio, 0.0) * peso
            resultado[i + k] = {
                "texto": palavra,
                "inicio_s": round(cursor, 3),
                "fim_s": round(cursor + duracao, 3),
            }
            cursor += duracao
        i = j
    return resultado
