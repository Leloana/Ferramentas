"""Letra embaixo das notas: Whisper marca o tempo de cada palavra na voz isolada,
o pyphen separa em sílabas e cada sílaba cai na nota cantada naquele momento.

Se houver a letra oficial (--letra arquivo.txt), ela corrige a grafia do que o Whisper ouviu
(mantendo os tempos do Whisper, porque gravação ao vivo repete/pula trechos).
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from pathlib import Path


def _norm(p: str) -> str:
    p = unicodedata.normalize("NFD", p.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in p if unicodedata.category(c) != "Mn"))


def palavras_com_tempo(voz_wav: Path, idioma: str = "pt", letra_oficial: str | None = None,
                       modelo: str = "large-v3-turbo") -> list[tuple[float, float, str]]:
    import torch  # noqa: F401  (carrega as DLLs do CUDA antes do ctranslate2 no Windows)
    from faster_whisper import WhisperModel

    print(f"[letra] transcrevendo voz com Whisper {modelo}...")
    try:
        wm = WhisperModel(modelo, device="cuda", compute_type="float16")
    except Exception as e:  # sem CUDA: CPU (mais lento)
        print(f"[letra] CUDA falhou ({e}); usando CPU")
        wm = WhisperModel(modelo, device="cpu", compute_type="int8")
    prompt = None
    if letra_oficial:
        prompt = " ".join(letra_oficial.split())[:600]
    import librosa  # o leitor do faster-whisper (PyAV) quebra em versões novas do av
    audio, _ = librosa.load(str(voz_wav), sr=16000, mono=True)
    # sem VAD: o filtro de voz do Whisper corta trechos cantados (ele foi feito pra fala)
    segs, _ = wm.transcribe(audio, language=idioma, word_timestamps=True, vad_filter=False,
                            initial_prompt=prompt, condition_on_previous_text=False, beam_size=5)
    palavras = []
    for s in segs:
        txt = s.text.strip()
        letras_txt = re.sub(r"[^A-Za-zÀ-ÿ]", "", txt)
        if (s.no_speech_prob > 0.6 or s.avg_logprob < -1.2 or not letras_txt
                or (letras_txt.isupper() and len(letras_txt) > 3)  # alucinação típica: "A CIDADE NO BRASIL"
                or _norm(txt) in {"musica", "legenda", "obrigado", "aplausos", "risos"}):
            continue
        for w in s.words or []:
            t = w.word.strip()
            if t and w.probability > 0.15:
                palavras.append((float(w.start), float(w.end), t))
    print(f"[letra] {len(palavras)} palavras com tempo")
    if letra_oficial:
        palavras = _corrigir_grafia(palavras, letra_oficial)
    return palavras


def _corrigir_grafia(palavras, letra: str):
    """Troca as palavras ouvidas pelas da letra oficial onde a sequência bate (mesmo tamanho)."""
    oficiais = re.findall(r"[\wÀ-ÿ'-]+[,.!?;:]?", letra)
    a = [_norm(p[2]) for p in palavras]
    saida = list(palavras)
    trocas = 0
    # a letra pode repetir na gravação: alinha contra a letra repetida 3x
    b_txt = oficiais * 3
    b = [_norm(x) for x in b_txt]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("equal", "replace") and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                ini, fim, _ = saida[i1 + k]
                nova = b_txt[j1 + k]
                if op == "replace" and difflib.SequenceMatcher(a=a[i1 + k], b=b[j1 + k]).ratio() < 0.5:
                    continue
                saida[i1 + k] = (ini, fim, nova)
                trocas += op == "replace"
    print(f"[letra] grafia corrigida pela letra oficial em {trocas} palavras")
    return saida


def silabas(palavra: str) -> list[str]:
    import pyphen
    d = pyphen.Pyphen(lang="pt_BR", left=1, right=1)
    pont = ""
    m = re.match(r"^(.*?)([,.!?;:]*)$", palavra)
    if m:
        palavra, pont = m.group(1), m.group(2)
    partes = d.inserted(palavra).split("-") if palavra else [palavra]
    partes = [p for p in partes if p] or [palavra]
    partes[-1] += pont
    return partes


def letra_nas_notas(notas_q, palavras) -> dict[int, str]:
    """notas_q: (ini_tempo, fim_tempo, midi, ini_s, fim_s). Devolve {índice_nota: texto}.

    Alinhamento global (programação dinâmica): as sílabas, em ordem, caem nas notas cujo
    ataque está mais perto do tempo estimado da sílaba; uma sílaba por nota, notas sem sílaba
    viram melisma. Se faltar nota, a sílaba se junta à anterior (com penalidade).
    Texto com hífen ("tris-", "-te-", "-za") vira sílaba ligada no MusicXML."""
    import numpy as np

    t_nota = np.array([n[3] for n in notas_q])
    if not len(t_nota):
        return {}
    # sílabas com tempo estimado (divide a palavra igualmente) e marca de início/fim de palavra
    sil = []  # (tempo, texto, j, k)
    for w_ini, w_fim, w in palavras:
        if np.min(np.abs(t_nota - w_ini)) > 0.8:  # nenhuma nota cantada perto: descarta
            continue
        partes = silabas(w)
        k = len(partes)
        dur = max(w_fim - w_ini, 0.05)
        for j, parte in enumerate(partes):
            sil.append((w_ini + dur * j / k, parte, j, k))
    S, N = len(sil), len(t_nota)
    if not S:
        return {}
    ts = np.array([x[0] for x in sil])
    custo = np.minimum(np.abs(ts[:, None] - t_nota[None, :]), 2.0)  # S x N
    JUNTA = 0.35  # custo de pôr 2 sílabas na mesma nota

    best = np.full((S, N), np.inf)
    de = np.zeros((S, N), dtype=np.int64)  # nota da sílaba anterior (-1 = mesma nota)
    best[0] = custo[0]
    for i in range(1, S):
        prev = best[i - 1]
        # menor custo anterior estritamente antes de j (prefixo mínimo deslocado)
        pm = np.minimum.accumulate(prev)
        arg = np.zeros(N, dtype=np.int64)
        a = 0
        for j in range(N):
            if prev[j] <= prev[a]:
                a = j
            arg[j] = a
        antes = np.concatenate([[np.inf], pm[:-1]])
        antes_arg = np.concatenate([[0], arg[:-1]])
        mesma = prev + JUNTA
        usa_mesma = mesma < antes
        best[i] = custo[i] + np.where(usa_mesma, mesma, antes)
        de[i] = np.where(usa_mesma, -1, antes_arg)
    j = int(np.argmin(best[-1]))
    alvo = [0] * S
    for i in range(S - 1, -1, -1):
        alvo[i] = j
        if i:
            j = j if de[i, j] == -1 else int(de[i, j])

    letras: dict[int, list[str]] = {}
    for (_, parte, jj, k), nota in zip(sil, alvo):
        txt = ("-" if jj > 0 else "") + parte + ("-" if jj < k - 1 else "")
        letras.setdefault(nota, []).append(txt)
    saida = {}
    for i, partes in letras.items():
        txt = partes[0]  # várias sílabas na mesma nota: "-da-" + "-de" -> "-dade"
        for p_ in partes[1:]:
            if txt.endswith("-") and p_.startswith("-"):
                txt = txt[:-1] + p_[1:]
            else:
                txt = txt.rstrip("-") + " " + p_.lstrip("-")
        saida[i] = txt
    return saida
