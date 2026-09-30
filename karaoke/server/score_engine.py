import logging
import re

from rapidfuzz import fuzz

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
    t = text.lower().strip()
    t = t.replace("-", " ")  # hífen vira espaço antes de limpar
    t = re.sub(r'[^\w\s]', '', t)
    t = t.strip()
    return _normalization_map(language).get(t, t)


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

    # B. Merge de fragmentos vocálicos
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

    for i, exp_word_data in enumerate(expected_timed):
        exp_word = expected_words[i]
        best_match_idx = -1
        best_ratio = 0
        
        for j, trans_word_data in enumerate(transcribed_clean):
            if j in consumed_indices:
                continue
            
            # token_sort_ratio lida melhor com variações fonéticas
            ratio = fuzz.token_sort_ratio(exp_word, trans_word_data["word"])
            if ratio > best_ratio:
                best_ratio = ratio
                best_match_idx = j
                if ratio == 100:
                    break
        
        word_points = 0.0
        if best_ratio >= FUZZY_FULL_MATCH:
            word_points = 1.0
            consumed_indices.add(best_match_idx)
        elif best_ratio >= FUZZY_HALF_MATCH:
            word_points = 0.5
            consumed_indices.add(best_match_idx)

        if word_points > 0 and best_match_idx != -1 and apply_timing:
            actual_start = transcribed_clean[best_match_idx]["start"]
            timing_pairs.append((exp_word_data["expected_start"], actual_start))
            diff = abs(actual_start - exp_word_data["expected_start"])
            if diff < TIMING_TOLERANT_SEC:
                pass
            elif diff <= TIMING_LENIENT_SEC:
                word_points *= TIMING_PENALTY_MID
            else:
                word_points *= TIMING_PENALTY_FAR

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
    n_transcribed = len(transcribed_clean)
    if n_expected > 0 and n_transcribed > n_expected * PRECISION_ALLOWANCE:
        precision_factor = max(
            PRECISION_MIN_FACTOR,
            (n_expected * PRECISION_ALLOWANCE) / n_transcribed,
        )

    final_score = base_score * tempo_factor * precision_factor

    return {
        "score": round(final_score, 1),
        "transcription": " ".join([w["word"] for w in transcribed_clean]),
        "matched_words": len(consumed_indices) + rescued_count,
        "total_expected": len(expected_words),
        "tempo_factor": round(tempo_factor, 3),
        "precision_factor": round(precision_factor, 3),
        "scoring_mode": scoring_mode
    }