import logging
import re
from collections import Counter
from functools import lru_cache

from rapidfuzz import fuzz

from lyrics_text import is_japanese, ja_reading
from phonetic import phonetic_key

logger = logging.getLogger(__name__)

# Limiares de scoring (extraídos para facilitar tuning)
FUZZY_FULL_MATCH = 70
# Meio ponto a partir de 67: com 50, palavras sem relação e de tamanho parecido
# ("cheirando"≈"cidade", "brilho"≈"isso") pontuavam e letra trocada tirava ~70.
# Erro de uma letra em palavra de 4+ letras ainda vale meio; em palavra de 3
# ("ele"→"ela", 66,7) não — custa ~0,2 ponto no canto certo e 2 na letra errada.
FUZZY_HALF_MATCH = 67
LEAKAGE_PER_WORD_MATCH = 80
LEAKAGE_GROUP_MATCH = 0.8
TIMING_TOLERANT_SEC = 1.0
TIMING_LENIENT_SEC = 2.5
TIMING_PENALTY_MID = 0.85
TIMING_PENALTY_FAR = 0.65
SANDWICH_THRESHOLD = 0.4
MAX_LEAKAGE_LOOKBACK = 6

# Pronúncia (phonetic.py): o Whisper escreve parecido com o que foi cantado
# ("chuva"→"xuva", "Belisha"→"belly shot"). Chaves de som com PHONETIC_MATCH ou
# mais valem palavra certa; chave curta ("the", "a") não decide nada.
PHONETIC_MATCH = 85
PHONETIC_MIN_KEY = 3
# ...e a escrita não pode estar longe demais: o Metaphone joga fora as vogais e
# "smacks you in" emendado soava como "magazine" (escrita 42; "belly shot" ×
# "Belisha" tem 62, "still" × "steel" 60, "xuva" × "chuva" 67)
PHONETIC_MIN_SPELLING = 55
# Emendas: até SPAN_MAX palavras de um lado contra uma do outro ("praquefazer" ×
# "pra que fazer", "belly shot" × "Belisha"). Só trechos longos e que batem forte:
# "a mim" × "mim" ganharia o "a" de graça.
SPAN_MAX = 3
SPAN_MIN_LETTERS = 7
SPAN_MATCH = 85

# Penalidade de andamento global: pune comprimir/esticar a linha inteira
# (ex.: ler todas as palavras correndo no início). Compara o "vão" de tempo
# cantado com o esperado entre a primeira e a última palavra casada.
TEMPO_MIN_EXPECTED_SPAN = 0.8   # vãos esperados menores que isso não punem tempo
TEMPO_WEIGHT = 0.35             # peso do andamento no score final (até -35%)
TEMPO_DEADZONE = 0.95           # acima disso considera-se andamento correto
TEMPO_ABS_TOLERANCE_SEC = 0.6   # encolhimento do vão perdoado (erro dos tempos do Whisper)

# Penalidade de precisão: pune excesso de palavras cantadas (repetir a mesma
# frase várias vezes). Uma margem evita punir hesitações/variações pequenas.
PRECISION_ALLOWANCE = 1.3       # margem de palavras extras sem punição
PRECISION_MIN_FACTOR = 0.2      # piso da penalidade de precisão

# Normalização acústica por idioma. Manter mapas separados evita colisões
# entre línguas (ex.: "a"->"ah" só faz sentido em PT, "know"->"no" só em EN).
_ACOUSTIC_EN = {
    "theres": "there", "there's": "there", "their": "there", "theyre": "there", "they're": "there",
    "youre": "your", "you're": "your",
    "im": "i", "i'm": "i",
    "its": "it", "it's": "it",
    "dont": "do", "don't": "do",
    "cant": "can", "can't": "can",
    "id": "i", "i'd": "i",
    "weve": "we", "we've": "we",
    "ive": "i", "i've": "i",
    "youll": "you", "you'll": "you",
    "theyll": "they", "they'll": "they",
    "shes": "she", "she's": "she",
    "hes": "he", "he's": "he",
    "thats": "that", "that's": "that",
    "whats": "what", "what's": "what",
    "lets": "let", "let's": "let",
    "too": "to", "two": "to",
    "threw": "through",
    "hear": "here",
    "know": "no",
    "sea": "see",
    "write": "right",
    "hour": "our",
    "four": "for", "fore": "for",
    "buy": "by", "bye": "by",
    "bee": "be",
    "inn": "in",
    "sun": "son",
    "sum": "some",
    "won": "one",
    "knew": "new",
    "knight": "night",
    "sew": "so", "sow": "so",
    "knot": "not",
}

_ACOUSTIC_PT = {
    "mas": "mais",
    "é": "eh",      # só com acento
    "há": "ah",     # só com acento
    # crase: o Whisper escreve "a"/"as" (e "a" x "à" dava 0)
    "à": "a",
    "às": "as",
    # fala cantada: letra formal × o que o Whisper escreve (e vice-versa)
    "tá": "está",
    "tô": "estou",
    "cê": "você",
    "ocê": "você",
    "pra": "para",
}

# Números por extenso (o Whisper às vezes escreve "2" onde a letra diz "dois")
_NUMBERS = {
    "pt": ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez",
           "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove", "vinte"],
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
           "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"],
}

# Mapa default conservador (usado quando idioma não é informado) — só os
# casos EN/PT que não conflitam entre si.
ACOUSTIC_NORMALIZATION = {**_ACOUSTIC_EN}

VOCAL_FRAGMENTS = {"ah", "oh", "eh", "hm", "mm", "uh", "aah", "ohh", "hmm"}

def filter_vocal_fragments(transcribed_words):
    filtered = []
    for i, w in enumerate(transcribed_words):
        word = w["word"].lower().strip()
        if word in VOCAL_FRAGMENTS and i > 0:
            # Ignora fragmento vocal que provavelmente é extensão da palavra anterior
            continue
        filtered.append(w)
    return filtered

def merge_vocal_fragments(transcribed_words, lyric_words: frozenset = frozenset()):
    """Cola vogal esticada ("ooh", "a") na palavra anterior.

    `lyric_words` (já passadas pelo clean_text) ficam de fora: "é", "eu", "a",
    "I" cantados onde a letra pede são palavras, não fragmentos.
    """
    merged = []
    for w in transcribed_words:
        word = w["word"].lower().strip()
        is_fragment = word in VOCAL_FRAGMENTS or (len(word) <= 2 and re.match(r'^[aeiouáéíóúãõ]+$', word))
        if is_fragment and lyric_words and (word in lyric_words or re.sub(r'[^\w]', '', word) in lyric_words):
            is_fragment = False
        if merged and is_fragment:
            merged[-1] = {**merged[-1], "end": w.get("end", merged[-1].get("end"))}
        else:
            merged.append(w)
    return merged

def _normalization_map(language: str | None) -> dict:
    if language and language.lower().startswith("pt"):
        return {**_ACOUSTIC_EN, **_ACOUSTIC_PT}
    return _ACOUSTIC_EN


def clean_text(text, language=None):
    if not text:
        return ""
    # Japonês compara pela leitura: o STT escreve a mesma palavra em kanji ou kana.
    if is_japanese(language):
        return ja_reading(text)
    t = text.lower().strip()
    t = t.replace("-", " ")  # hífen vira espaço antes de limpar
    t = re.sub(r'[^\w\s]', '', t)
    t = t.strip()
    if t.isdigit():
        names = _NUMBERS["pt" if language and language.lower().startswith("pt") else "en"]
        if int(t) < len(names):
            t = names[int(t)]
    return _normalization_map(language).get(t, t)


def join_split_words(transcribed_words):
    """Cola "-se"/"-lo" na palavra anterior: o Whisper devolve "Dá" + "-se",
    a letra tem "Dá-se" (virava 2 tokens contra 1 e a nota caía para ~43)."""
    out = []
    for w in transcribed_words:
        word = (w.get("word") or "").strip()
        if out and word.startswith("-") and len(word) > 1:
            prev = out[-1]
            out[-1] = {**prev, "word": prev["word"].rstrip() + word, "end": w.get("end", prev.get("end"))}
        else:
            out.append(w)
    return out


DUPLICATE_LOW_PROB = 0.1
DUPLICATE_TRUSTED_PROB = 0.3


def drop_unreliable_duplicates(transcribed_words, language=None, expected_words=None):
    """Tira palavra quase sem confiança (<0.1) quando a mesma palavra também
    aparece com confiança (>=0.3): o Whisper às vezes "ouve" o verso duas vezes
    e a cópia fantasma disparava a penalidade de precisão.

    `expected_words` (letra já limpa): palavra que a letra pede N vezes só perde
    a cópia fraca quando já há N cópias confiáveis ("The flan in the face").
    """
    trusted = Counter(
        clean_text(w["word"], language)
        for w in transcribed_words
        if w.get("probability", 1.0) >= DUPLICATE_TRUSTED_PROB
    )
    wanted = Counter(expected_words or ())
    return [
        w for w in transcribed_words
        if not (w.get("probability", 1.0) < DUPLICATE_LOW_PROB
                and trusted[clean_text(w["word"], language)] >= max(1, wanted[clean_text(w["word"], language)]))
    ]


def _word_points(ratio: float, expected_start: float, actual_start: float, apply_timing: bool) -> float:
    """Pontos de um par letra × transcrição: acerto da palavra × penalidade de tempo."""
    if ratio >= FUZZY_FULL_MATCH:
        points = 1.0
    elif ratio >= FUZZY_HALF_MATCH:
        points = 0.5
    else:
        return 0.0
    if apply_timing:
        diff = abs(actual_start - expected_start)
        if diff > TIMING_LENIENT_SEC:
            points *= TIMING_PENALTY_FAR
        elif diff >= TIMING_TOLERANT_SEC:
            points *= TIMING_PENALTY_MID
    return points


@lru_cache(maxsize=4096)
def _key(text: str, language: str | None) -> str:
    return phonetic_key(text, language)


def _sounds_alike(a: str, b: str, language: str | None) -> bool:
    if fuzz.ratio(a, b) < PHONETIC_MIN_SPELLING:
        return False
    ka, kb = _key(a, language), _key(b, language)
    return len(ka) >= PHONETIC_MIN_KEY and len(kb) >= PHONETIC_MIN_KEY and fuzz.ratio(ka, kb) >= PHONETIC_MATCH


def _span_matches(joined_expected: str, joined_heard: str, language: str | None) -> bool:
    """Trecho emendado de um lado × palavras soltas do outro, comparados sem espaço."""
    a, b = len(joined_expected), len(joined_heard)
    if a < SPAN_MIN_LETTERS or b < SPAN_MIN_LETTERS or min(a, b) < 0.7 * max(a, b):
        return False
    return fuzz.ratio(joined_expected, joined_heard) >= SPAN_MATCH or _sounds_alike(joined_expected, joined_heard, language)


def match_in_order(expected_words: list[str], expected_timed: list[dict],
                   transcribed_clean: list[dict], apply_timing: bool,
                   alternatives: list[tuple[str, ...]] | None = None,
                   language: str | None = None) -> list[tuple[float, tuple[int, ...]]]:
    """Casa a letra com a transcrição sem cruzar pares: (pontos, índices transcritos) por palavra.

    Programação dinâmica que maximiza a soma dos pontos com pares em ordem nos
    dois lados. A versão gulosa pegava a melhor palavra em qualquer posição:
    "door the at wolf the" tirava 97 em "a wolf at the door".
    Além do par 1×1 (escrita ou pronúncia), aceita emendas de até SPAN_MAX
    palavras contra uma (fora do japonês, que já compara pela leitura).
    """
    n, m = len(expected_words), len(transcribed_clean)
    sound = not is_japanese(language)
    heard = [w["word"] for w in transcribed_clean]
    pts = [[0.0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            ratio = fuzz.token_sort_ratio(expected_words[i], heard[j])
            if alternatives:  # japonês: outra leitura do mesmo kanji (lyrics_text.ja_readings)
                ratio = max([ratio] + [fuzz.token_sort_ratio(a, heard[j]) for a in alternatives[i]])
            if sound and ratio < FUZZY_FULL_MATCH and _sounds_alike(expected_words[i], heard[j], language):
                ratio = FUZZY_FULL_MATCH
            pts[i][j] = _word_points(ratio, expected_timed[i]["expected_start"],
                                     transcribed_clean[j]["start"], apply_timing)

    def span_points(i: int, j: int, a: int, b: int) -> float:
        """Pontos de `a` palavras da letra emendadas contra `b` ouvidas (uma das duas é 1)."""
        if i + a > n or j + b > m:
            return 0.0
        # uma parte já bate sozinha com o outro lado ("felizes" × "E felizes"): a emenda
        # só ganharia de graça a palavra do lado
        parts = ([(expected_words[i + k], heard[j]) for k in range(a)] if a > 1
                 else [(expected_words[i], heard[j + k]) for k in range(b)])
        if any(fuzz.token_sort_ratio(x, y) >= FUZZY_FULL_MATCH for x, y in parts):
            return 0.0
        if not _span_matches("".join(expected_words[i:i + a]), "".join(heard[j:j + b]), language):
            return 0.0
        return a * _word_points(100, expected_timed[i]["expected_start"], transcribed_clean[j]["start"], apply_timing)

    spans = [(1, k) for k in range(2, SPAN_MAX + 1)] + [(k, 1) for k in range(2, SPAN_MAX + 1)] if sound else []
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            # empate: casa o par, depois a emenda, depois pula a ouvida e por último a da
            # letra (a falta fica no fim do verso, como sempre foi — o "sanduíche" abaixo
            # resgataria uma falta no meio)
            options = []
            if pts[i][j] > 0:
                options.append((pts[i][j] + best[i + 1][j + 1], (1, 1, pts[i][j])))
            for a, b in spans:
                got = span_points(i, j, a, b)
                if got > 0:
                    options.append((got + best[i + a][j + b], (a, b, got / a)))
            options += [(best[i][j + 1], "skip_heard"), (best[i + 1][j], "skip_expected")]
            best[i][j], move[i][j] = max(options, key=lambda o: o[0])
    out, i, j = [], 0, 0
    while i < n:
        step = move[i][j] if j < m else "skip_expected"
        if step == "skip_heard":
            j += 1
        elif step == "skip_expected":
            out.append((0.0, ()))
            i += 1
        else:
            a, b, each = step
            used = tuple(range(j, j + b))
            out.extend([(each, used)] * a)
            i, j = i + a, j + b
    return out


def calculate_score(expected_timed: list[dict], transcribed_words: list[dict], prev_expected_words: list[str] = None, language: str | None = None, scoring_mode: str = "timing") -> dict:
    """Calcula a nota de um segmento cantado.

    scoring_mode:
        "timing" (padrão) — palavras acertadas + tempo correto. Aplica a
            penalidade de tempo por palavra e a penalidade de andamento global.
        "words" — somente palavras acertadas. Ignora qualquer penalidade de
            tempo (por palavra e de andamento), pontuando apenas pelo acerto
            das palavras.
    """
    if not expected_timed:
        return {"score": 0, "details": "Nenhuma letra esperada."}

    apply_timing = scoring_mode != "words"

    # A. Detecção e Remoção de Vazamento (Perdão Inteligente)
    if prev_expected_words and transcribed_words:

        current_text = " ".join(w["word"] for w in expected_timed).lower()
        prev_text = " ".join(prev_expected_words).lower()

        if fuzz.ratio(current_text, prev_text) > 80:
            logger.info("⏭️ [Perdão de Vazamento] Ignorado: versos muito similares ao anterior")
        else:
            prev_clean = [clean_text(w, language) for w in prev_expected_words if w]
            trans_clean = [clean_text(w["word"], language) for w in transcribed_words if w]

            max_overlap = min(len(prev_clean), len(trans_clean), MAX_LEAKAGE_LOOKBACK)
            overlap_found = 0

            # Checagem 1: sufixo exato do verso anterior (comportamento original)
            for k in range(max_overlap, 0, -1):
                prev_suffix = prev_clean[-k:]
                trans_prefix = trans_clean[:k]
                match_count = sum(
                    1 for idx in range(k)
                    if fuzz.token_sort_ratio(prev_suffix[idx], trans_prefix[idx]) >= LEAKAGE_PER_WORD_MATCH
                )
                if match_count / k >= LEAKAGE_GROUP_MATCH:
                    overlap_found = k
                    break

            # Checagem 2: qualquer trecho do verso anterior no início da transcrição
            if overlap_found == 0:
                for start_idx in range(len(prev_clean) - 1):
                    for k in range(2, min(MAX_LEAKAGE_LOOKBACK, len(trans_clean) + 1)):
                        prev_slice = prev_clean[start_idx:start_idx + k]
                        trans_prefix = trans_clean[:k]
                        if len(prev_slice) != k:
                            break
                        match_count = sum(
                            1 for idx in range(k)
                            if fuzz.token_sort_ratio(prev_slice[idx], trans_prefix[idx]) >= LEAKAGE_PER_WORD_MATCH
                        )
                        if match_count / k >= LEAKAGE_GROUP_MATCH:
                            overlap_found = k
                            break
                    if overlap_found > 0:
                        break

            # O trecho "vazado" também é o começo do verso atual (repetição, verso
            # que abre igual ao anterior): foi cantado agora e não se remove.
            if overlap_found > 0:
                current_clean = [clean_text(w["word"], language) for w in expected_timed]
                k = overlap_found
                own_match = sum(
                    1 for idx in range(min(k, len(current_clean)))
                    if fuzz.token_sort_ratio(current_clean[idx], trans_clean[idx]) >= LEAKAGE_PER_WORD_MATCH
                )
                if own_match / k >= LEAKAGE_GROUP_MATCH:
                    logger.info(f"⏭️ [Perdão de Vazamento] Ignorado: {k} palavra(s) também abrem o verso atual")
                    overlap_found = 0

            if overlap_found > 0:
                leaked = [w['word'] for w in transcribed_words[:overlap_found]]
                logger.info(f"🛡️ [Perdão de Vazamento] {overlap_found} palavras vazadas do verso anterior: {leaked}")
                transcribed_words = transcribed_words[overlap_found:]

    # B. Palavras quebradas pelo hífen e cópias fantasma de baixa confiança
    transcribed_words = drop_unreliable_duplicates(
        join_split_words(transcribed_words), language,
        [clean_text(w["word"], language) for w in expected_timed])

    # Merge de fragmentos vocálicos
    lyric_words = frozenset(
        {clean_text(w["word"], language) for w in expected_timed}
        | {re.sub(r"[^\w]", "", w["word"].lower()) for w in expected_timed}
    )
    transcribed_words = merge_vocal_fragments(transcribed_words, lyric_words)

    # Tokenização e limpeza acústica normalizada
    expected_words = [clean_text(w["word"], language) for w in expected_timed]
    transcribed_clean = [{"word": clean_text(w["word"], language), "start": w["start"]} for w in transcribed_words]
    word_scores = []
    consumed_indices = set()
    timing_pairs = []  # (expected_start, actual_start) das palavras casadas
    spans_heard = set()  # emendas "belly shot" × "Belisha": várias ouvidas valem uma

    alternatives = None
    if is_japanese(language):
        from lyrics_text import ja_readings

        alternatives = [ja_readings(w["word"]) for w in expected_timed]
    for i, (word_points, used) in enumerate(match_in_order(expected_words, expected_timed, transcribed_clean,
                                                           apply_timing, alternatives, language)):
        if used:
            consumed_indices.update(used)
            if len(used) > 1:
                spans_heard.add(used)
            if apply_timing:
                timing_pairs.append((expected_timed[i]["expected_start"], transcribed_clean[used[0]]["start"]))
        word_scores.append(word_points)

    # Sandwich Recovery: 1 ou 2 palavras erradas cercadas por corretas são "resgatadas"
    rescued_count = 0
    if len(word_scores) >= 3:
        for idx in range(1, len(word_scores) - 1):
            if (word_scores[idx] < SANDWICH_THRESHOLD
                    and word_scores[idx - 1] >= SANDWICH_THRESHOLD
                    and word_scores[idx + 1] >= SANDWICH_THRESHOLD):
                word_scores[idx] = 1.0
                rescued_count += 1
        for idx in range(1, len(word_scores) - 2):
            if (word_scores[idx] < SANDWICH_THRESHOLD and word_scores[idx + 1] < SANDWICH_THRESHOLD
                    and word_scores[idx - 1] >= SANDWICH_THRESHOLD
                    and word_scores[idx + 2] >= SANDWICH_THRESHOLD):
                word_scores[idx] = 0.8
                word_scores[idx + 1] = 0.8
                rescued_count += 2

    total_points = sum(word_scores)
    base_score = (total_points / len(expected_words)) * 100

    # Penalidade de andamento global: ler a linha inteira correndo encolhe o
    # "vão" entre a primeira e a última palavra casada. Um offset constante
    # (atraso parelho) não pune aqui — isso é tratado por palavra acima.
    # Só compressão pune: canto certo sai em média 1,33x o vão esperado (o
    # Whisper espalha mais os tempos que o alinhamento da letra) e esticar
    # demais já cai na penalidade por palavra. Os primeiros
    # TEMPO_ABS_TOLERANCE_SEC de encolhimento são imprecisão de medição.
    tempo_factor = 1.0
    if apply_timing and len(timing_pairs) >= 2:
        exp_span = max(p[0] for p in timing_pairs) - min(p[0] for p in timing_pairs)
        act_span = max(p[1] for p in timing_pairs) - min(p[1] for p in timing_pairs)
        if exp_span >= TEMPO_MIN_EXPECTED_SPAN and act_span < exp_span:
            closeness = min(1.0, max(0.0, (act_span + TEMPO_ABS_TOLERANCE_SEC) / exp_span))
            if closeness < TEMPO_DEADZONE:
                tempo_factor = (1.0 - TEMPO_WEIGHT) + TEMPO_WEIGHT * closeness

    # Penalidade de precisão: pune excesso de palavras cantadas (repetir a mesma
    # frase). Até expected * PRECISION_ALLOWANCE palavras passam sem punição.
    precision_factor = 1.0
    n_expected = len(expected_words)
    n_transcribed = len(transcribed_clean) - sum(len(used) - 1 for used in spans_heard)
    if n_expected > 0 and n_transcribed > n_expected * PRECISION_ALLOWANCE:
        precision_factor = max(
            PRECISION_MIN_FACTOR,
            (n_expected * PRECISION_ALLOWANCE) / n_transcribed,
        )

    final_score = base_score * tempo_factor * precision_factor

    return {
        "score": round(final_score, 1),
        "transcription": " ".join([w["word"] for w in transcribed_clean]),
        # acerto de cada palavra ouvida, na ordem da transcrição: a TV pinta o "Ouvi:" por
        # aqui (em japonês a comparação é em romaji e a letra na tela está em kanji)
        "heard_hits": [j in consumed_indices for j in range(len(transcribed_clean))],
        "matched_words": len(consumed_indices) + rescued_count,
        "total_expected": len(expected_words),
        "tempo_factor": round(tempo_factor, 3),
        "precision_factor": round(precision_factor, 3),
        "scoring_mode": scoring_mode
    }