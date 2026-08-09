import logging
import os
import re
import threading

os.environ.setdefault("COQUI_TOS_AGREED", "1")

import numpy as np
import torch
from TTS.api import TTS

import config
from engine.forced_aligner import ForcedAligner

logger = logging.getLogger("TTSPlatform")

# Bug conhecido do XTTS-v2 em português: o modelo às vezes verbaliza "." como
# a palavra "ponto" em vez de tratá-lo como pausa (coqui-ai/TTS#2952). O time
# da Coqui confirma que trocar o ponto final por "|" evita a verbalização e
# ainda produz a pausa esperada. Preserva pontos de números decimais (ex: "3.14").
_PONTO_FINAL_RE = re.compile(r"(?<!\d)\.|\.(?!\d)")

# Gap inserido manualmente entre frases sintetizadas separadamente. Medido
# empiricamente: cada frase sintetizada isolada já vem com silêncio próprio
# de abertura/fechamento; sem cortar isso primeiro, esse gap SOMA em cima
# desse silêncio nativo e a pausa final fica bem mais longa que uma pausa
# natural de "." (cheguei a medir 0.82s vs os ~0.55-0.6s de uma pausa natural
# dentro de uma única chamada contínua). Por isso `synthesize` apara o
# silêncio de cada frase (`_trim_silencio`) antes de somar este gap.
_GAP_ENTRE_FRASES_S = 0.35
_LIMIAR_SILENCIO_RMS = 0.01
_JANELA_TRIM_S = 0.02
# Margem mantida além do ponto onde o RMS cruza o limiar, pra não cortar
# rente em cima de consoantes finais/decaimento natural mais baixo (ex.: "s"
# no fim de uma palavra pode cair abaixo do limiar antes do som acabar de
# verdade). Fade curto pra suavizar a transição pro silêncio em vez de um
# corte abrupto (que soa como um "clique"/frase cortada mesmo quando nenhum
# fonema é removido).
_MARGEM_TRIM_S = 0.08
_FADE_S = 0.03

# Silêncio inserido antes da primeira frase do áudio final. Diferente das
# frases seguintes (que já ganham `_GAP_ENTRE_FRASES_S` de silêncio puro na
# frente), a primeira frase vai direto pro início do arquivo — se o XTTS-v2
# gerar pouco ou nenhum silêncio nativo de abertura nessa chamada específica,
# `_trim_silencio` não tem margem sobrando pra recuar e o fade-in de
# `_FADE_S` acaba rampando em cima do início real da primeira palavra em vez
# de silêncio, cortando o começo dela perceptivelmente.
_LEAD_IN_S = 0.15

# Mesma regra de `scripts/montar_video.py:_limpar_pontuacao` — precisa ficar
# em sincronia com aquele arquivo: é o que garante que a lista de palavras
# passada pro alinhador (`ForcedAligner.align`) bate 1:1 com as palavras que
# `montar_video.py` vai agrupar em chunk de legenda depois.
_PONTUACAO_PALAVRA_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def _limpar_pontuacao(texto: str) -> str:
    sem_pontuacao = _PONTUACAO_PALAVRA_RE.sub(" ", texto)
    return re.sub(r"\s+", " ", sem_pontuacao).strip()


def _sanitizar_pontuacao_pt(text: str) -> str:
    return _PONTO_FINAL_RE.sub("|", text)


def _trim_silencio(wav: np.ndarray, sample_rate: int) -> np.ndarray:
    """Remove o silêncio nas bordas de um clipe sintetizado isoladamente.

    Necessário porque cada frase é sintetizada com sua própria chamada (ver
    `synthesize`), e o XTTS-v2 tende a incluir um silêncio de abertura/
    fechamento natural do próprio clipe — sem isso, concatenar vários clipes
    empilha esse silêncio nativo em cima do gap que inserimos entre eles.
    Mantém uma margem além do limiar de RMS e aplica um fade-out curto no
    final, pra não soar como a frase foi cortada bruscamente.
    """
    janela = int(sample_rate * _JANELA_TRIM_S)
    n_janelas = len(wav) // janela
    if n_janelas == 0:
        return wav
    rms = np.array([
        np.sqrt(np.mean(wav[i * janela:(i + 1) * janela] ** 2))
        for i in range(n_janelas)
    ])
    acima = np.where(rms >= _LIMIAR_SILENCIO_RMS)[0]
    if len(acima) == 0:
        return wav

    margem = int(sample_rate * _MARGEM_TRIM_S)
    inicio = max(0, acima[0] * janela - margem)
    fim = min((acima[-1] + 1) * janela + margem, len(wav))
    trecho = wav[inicio:fim].copy()

    fade_amostras = min(int(sample_rate * _FADE_S), len(trecho) // 2)
    if fade_amostras > 0:
        trecho[:fade_amostras] *= np.linspace(0.0, 1.0, fade_amostras)
        trecho[-fade_amostras:] *= np.linspace(1.0, 0.0, fade_amostras)
    return trecho


class TTSEngine:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        try:
            self.tts = TTS(config.XTTS_MODEL_NAME).to(self.device)
        except Exception as e:
            logger.warning(f"Falha ao carregar XTTS-v2 na GPU ({e}), caindo para CPU.")
            self.device = "cpu"
            self.tts = TTS(config.XTTS_MODEL_NAME).to("cpu")
        logger.info(f"XTTS-v2 carregado no dispositivo: {self.device}")
        # Alinhador de palavras roda sempre em CPU, independente de `self.device`
        # (ver `engine/forced_aligner.py`) — a VRAM já fica apertada só com o
        # XTTS-v2 quando o ComfyUI Desktop está aberto junto.
        self.aligner = ForcedAligner()

    def list_builtin_speakers(self):
        return list(self.tts.speakers or [])

    def synthesize(self, text, output_path, language=config.DEFAULT_LANGUAGE, speaker=None, speaker_wav=None, speed=1.0):
        # `speed` é nativo do XTTS-v2 (Xtts.inference), não um ajuste de
        # velocidade de reprodução: ele escala o length_scale usado pelo
        # próprio decoder durante a geração, então o áudio já sai mais rápido/
        # lento na fonte, sem stretch de pós-processamento nem mudança de
        # pitch. Faixa recomendada pela Coqui é ~0.5-2.0; fora de ~0.7-1.3 a
        # voz costuma degradar (artefatos, cadência robótica).
        kwargs = {"language": language, "speed": speed}
        if speaker_wav:
            kwargs["speaker_wav"] = str(speaker_wav)
        else:
            builtin = self.list_builtin_speakers()
            kwargs["speaker"] = speaker or (builtin[0] if builtin else None)

        # A troca de "." por "|" (bug do "ponto") precisa acontecer DEPOIS que
        # o texto já foi dividido em frases pelo segmentador da própria
        # biblioteca (`split_into_sentences`, baseado em pysbd) — esse
        # segmentador usa o ponto final pra achar os limites de frase. Se a
        # troca acontecesse antes, o texto inteiro vira uma "frase" só (sem
        # pontos pra dividir) e pode estourar o limite de 400 tokens do XTTS-v2
        # em textos longos. Por isso sintetizamos frase por frase e
        # concatenamos o áudio manualmente.
        frases = [f for f in self.tts.synthesizer.split_into_sentences(text) if f.strip()]

        sample_rate = self.tts.synthesizer.output_sample_rate
        gap = np.zeros(int(sample_rate * _GAP_ENTRE_FRASES_S))

        clipes = []
        for frase in frases:
            frase_tts = _sanitizar_pontuacao_pt(frase) if language.startswith("pt") else frase
            wav = self.tts.tts(text=frase_tts, split_sentences=False, **kwargs)
            clipes.append(_trim_silencio(np.asarray(wav), sample_rate))

        # Timestamps por frase (pro texto original, sem a troca "." -> "|"
        # que é só um workaround de pronúncia) — usados pra gerar legendas
        # sincronizadas sem precisar de um passo de transcrição/alinhamento
        # à parte: a gente já sabe exatamente onde cada frase começa/termina
        # porque foi a gente quem montou o áudio, frase por frase. Timestamp
        # por PALAVRA vem do alinhador forçado (`self.aligner`), rodado em
        # cima do próprio `clipe` já trimado — o resultado vem relativo ao
        # início do clipe, por isso soma `cursor_s` (que aqui ainda é o
        # início desta frase) pra virar timestamp absoluto na faixa final.
        partes = [np.zeros(int(sample_rate * _LEAD_IN_S))]
        timings = []
        cursor_s = _LEAD_IN_S
        for i, (frase, clipe) in enumerate(zip(frases, clipes)):
            duracao_s = len(clipe) / sample_rate
            palavras_frase = _limpar_pontuacao(frase).split()
            palavras_alinhadas = self.aligner.align(clipe, sample_rate, palavras_frase)
            palavras = [
                {
                    "texto": p["texto"],
                    "inicio_s": round(cursor_s + p["inicio_s"], 3),
                    "fim_s": round(cursor_s + p["fim_s"], 3),
                }
                for p in palavras_alinhadas
            ]
            timings.append({
                "texto": frase,
                "inicio_s": round(cursor_s, 3),
                "fim_s": round(cursor_s + duracao_s, 3),
                "palavras": palavras,
            })
            partes.append(clipe)
            cursor_s += duracao_s
            if i < len(clipes) - 1:
                partes.append(gap)
                cursor_s += _GAP_ENTRE_FRASES_S

        wav_final = np.concatenate(partes) if partes else np.zeros(1)
        self.tts.synthesizer.save_wav(wav=wav_final, path=str(output_path))
        return output_path, timings


_engine = None
_engine_lock = threading.Lock()


def get_tts_engine():
    # FastAPI roda rotas síncronas (como GET /api/voices) numa thread pool,
    # então requests concorrentes podem cair aqui ao mesmo tempo antes de
    # `_engine` ser setado. Sem lock, cada uma instancia seu próprio
    # TTSEngine (carregando o checkpoint do zero) em paralelo — reproduzido
    # na prática com um client fazendo poll agressivo em /api/voices durante
    # a subida do servidor, gerando dezenas de cargas concorrentes do XTTS-v2.
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = TTSEngine()
    return _engine
