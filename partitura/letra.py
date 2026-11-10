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


IDIOMA_DETECTADO = "pt"
_IDIOMAS_MISTO: list[str] = []


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
    # A letra oficial NÃO vai como prompt: testado em Rosa de Hiroshima, o prompt faz o Whisper misturar
    # versos ("Pensem nas meninas, mudas, telepáticas"). Ele transcreve livre e a grafia é corrigida depois.
    prompt = None
    import librosa  # o leitor do faster-whisper (PyAV) quebra em versões novas do av
    audio, _ = librosa.load(str(voz_wav), sr=16000, mono=True)
    # sem VAD: o filtro de voz do Whisper corta trechos cantados (ele foi feito pra fala)
    global IDIOMA_DETECTADO
    if idioma == "auto":
        # detecta o idioma olhando vários trechos com voz (o começo costuma ser só introdução
        # instrumental; detectar só por ele fez o Whisper "traduzir" Garota de Ipanema pro inglês)
        idioma, misto = _detectar_idioma(wm, audio)
    else:
        misto = False
    # música com dois idiomas (ex.: Getz/Gilberto, João em português e Astrud em inglês):
    # modo multilíngue troca de idioma por trecho em vez de traduzir tudo pro idioma principal
    segs, info = wm.transcribe(audio, language=None if misto else idioma, multilingual=misto,
                               word_timestamps=True, vad_filter=False, initial_prompt=prompt,
                               condition_on_previous_text=False, beam_size=5)
    IDIOMA_DETECTADO = idioma if idioma != "auto" else (info.language or "pt")
    if misto and _IDIOMAS_MISTO and "pt" in _IDIOMAS_MISTO[:2]:
        IDIOMA_DETECTADO = "pt"  # sílabas: regra do português serve razoavelmente pras palavras em inglês
    print(f"[letra] idioma: {IDIOMA_DETECTADO}")
    palavras = []
    rejeitados = []
    for s in segs:
        if _alucinacao(s):
            rejeitados.append((s.start, s.end))
            continue
        palavras += _palavras_do_segmento(s)
    # Trecho descartado como alucinação ("A CIDADE NO BRASIL" no lugar do 1º verso) costuma ter voz de
    # verdade: transcrito sozinho, sem o contexto da música inteira, o Whisper acerta. Segunda chance.
    recuperadas = 0
    for ini, fim in rejeitados:
        a = max(0.0, ini - 1.0)
        trecho = audio[int(a * 16000):int((fim + 1.0) * 16000)]
        if len(trecho) < 16000:
            continue
        segs2, _ = wm.transcribe(trecho, language=None if misto else idioma, multilingual=misto,
                                 word_timestamps=True, vad_filter=False, condition_on_previous_text=False,
                                 beam_size=5)
        for s2 in segs2:
            if not _alucinacao(s2):
                novas = [(i + a, f + a, t) for i, f, t in _palavras_do_segmento(s2)]
                palavras += novas
                recuperadas += len(novas)
    if rejeitados:
        print(f"[letra] {len(rejeitados)} trecho(s) alucinado(s) descartado(s); {recuperadas} palavras recuperadas na 2ª tentativa")
    palavras.sort()
    print(f"[letra] {len(palavras)} palavras com tempo")
    if letra_oficial:
        palavras = _corrigir_grafia(palavras, letra_oficial)
    return palavras


def _chave(t: str) -> str:
    """Nome pra comparar: sem acento, sem "(Remasterizado)", sem " - Ao Vivo"."""
    t = re.sub(r"[\(\[].*?[\)\]]", " ", t or "")
    t = re.sub(r"\s+[-–—]\s+.*$", " ", t)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", _norm_espacos(t))).strip()


def _norm_espacos(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def buscar_letra(titulo: str, artista: str, com_sincronizada: bool = False):
    """Letra oficial no LRCLIB (base aberta, a mesma do karaokê). Só aceita se título e artista batem.

    com_sincronizada=True devolve (letra, lrc_sincronizado|None); o LRC dá o início de cada verso
    pro alinhamento por janela (pode ser de outra gravação: o alinhador do karaokê confere)."""
    import json
    import urllib.parse
    import urllib.request
    if not titulo:
        return None
    t_q, a_q = _chave(titulo), _chave(artista)
    urls = []
    if artista:
        urls.append("https://lrclib.net/api/search?" + urllib.parse.urlencode({"artist_name": artista, "track_name": titulo}))
    urls.append("https://lrclib.net/api/search?" + urllib.parse.urlencode({"q": f"{titulo} {artista}".strip()}))
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Partitura/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                cands = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001  (sem internet etc.: segue sem letra oficial)
            print(f"[letra] LRCLIB indisponível ({e})")
            return (None, None) if com_sincronizada else None
        for c in cands or []:
            letra = (c.get("plainLyrics") or "").strip()
            if not letra or c.get("instrumental"):
                continue
            sim_t = difflib.SequenceMatcher(a=_chave(c.get("trackName", "")), b=t_q).ratio()
            sim_a = difflib.SequenceMatcher(a=_chave(c.get("artistName", "")), b=a_q).ratio() if a_q else 1.0
            if sim_t >= 0.8 and (sim_a >= 0.6 or a_q in _chave(c.get("artistName", ""))):
                print(f"[letra] letra oficial: LRCLIB \"{c.get('trackName')}\" de {c.get('artistName')}")
                if com_sincronizada:
                    return letra, (c.get("syncedLyrics") or "").strip() or None
                return letra
    print("[letra] letra oficial não encontrada no LRCLIB (segue só com o Whisper)")
    return (None, None) if com_sincronizada else None


def _alucinacao(s) -> bool:
    txt = s.text.strip()
    letras_txt = re.sub(r"[^A-Za-zÀ-ÿ]", "", txt)
    return (s.no_speech_prob > 0.6 or s.avg_logprob < -1.2 or not letras_txt
            or (letras_txt.isupper() and len(letras_txt) > 3)  # alucinação típica: "A CIDADE NO BRASIL"
            or _norm(txt) in {"musica", "legenda", "obrigado", "aplausos", "risos"}
            or _em_loop(txt, s.compression_ratio))


def _palavras_do_segmento(s) -> list[tuple[float, float, str]]:
    saida = []
    for w in s.words or []:
        t = w.word.strip()
        if len(t) > 24 or " " in t or "," in t.rstrip(",.!?;:"):  # "palavra" que é um loop inteiro
            continue
        if t and w.probability > 0.15:
            saida.append((float(w.start), float(w.end), t))
    return saida


def _detectar_idioma(wm, audio, janela_s: float = 30.0) -> str:
    """Idioma mais provável somando a detecção em até 6 janelas de 30 s onde a voz está mais alta."""
    import numpy as np
    sr = 16000
    n = int(janela_s * sr)
    janelas = [(i, float(np.sqrt(np.mean(audio[i:i + n] ** 2)))) for i in range(0, max(1, len(audio) - n // 2), n // 2)]
    melhores = sorted(janelas, key=lambda x: -x[1])[:6]
    votos: dict[str, float] = {}
    for i, _ in melhores:
        lang, prob, _ = wm.detect_language(audio[i:i + n])
        votos[lang] = votos.get(lang, 0.0) + prob
    ordem = sorted(votos.items(), key=lambda x: -x[1]) or [("pt", 1.0)]
    escolhido = ordem[0][0]
    misto = len(ordem) > 1 and ordem[1][1] >= 0.5 * ordem[0][1]
    global _IDIOMAS_MISTO
    _IDIOMAS_MISTO = [k for k, _ in ordem]
    print(f"[letra] idioma detectado: {escolhido}{' (misto)' if misto else ''} (votos: "
          + ", ".join(f"{k} {v:.1f}" for k, v in ordem[:3]) + ")")
    return escolhido, misto


def _em_loop(txt: str, compressao: float) -> bool:
    """Alucinação clássica do Whisper em trecho sem voz: "quatro, quatro, quatro, ..." """
    if compressao > 2.4:
        return True
    ws = [_norm(w) for w in txt.split()]
    seguidas = 1
    for a, b in zip(ws, ws[1:]):
        seguidas = seguidas + 1 if a and a == b else 1
        if seguidas >= 4:
            return True
    return False


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


PYPHEN_LANG = {"pt": "pt_BR", "en": "en_US", "es": "es", "fr": "fr", "it": "it_IT", "de": "de_DE"}


def silabas(palavra: str, idioma: str = "pt") -> list[str]:
    import pyphen
    borda = 1 if idioma in ("pt", "es", "it") else 2  # inglês: nada de "friend-s", "o-h"
    d = pyphen.Pyphen(lang=PYPHEN_LANG.get(idioma, idioma), left=borda, right=borda)
    pont = ""
    m = re.match(r"^(.*?)([,.!?;:]*)$", palavra)
    if m:
        palavra, pont = m.group(1), m.group(2)
    partes = d.inserted(palavra).split("-") if palavra else [palavra]
    partes = [p for p in partes if p] or [palavra]
    partes[-1] += pont
    return partes


def letra_nas_notas(notas_q, palavras, idioma: str = "pt") -> dict[int, list[str]]:
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
        partes = silabas(w, idioma)
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

    # {nota: [sílabas]} — várias sílabas na mesma nota viram notas repetidas na partitura (gerar.py);
    # o limite de 4 palavras por nota só barra lixo (alucinação que escapou dos filtros)
    letras: dict[int, list[str]] = {}
    pulando = False
    for (_, parte, jj, k), nota in zip(sil, alvo):
        if jj == 0:
            pulando = sum(1 for x in letras.get(nota, []) if not x.startswith("-")) >= 4
        if pulando:
            continue
        txt = ("-" if jj > 0 else "") + parte + ("-" if jj < k - 1 else "")
        letras.setdefault(nota, []).append(txt)
    saida = letras
    return saida
