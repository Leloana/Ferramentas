import logging
import re

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)

# Limiares de scoring (extraídos para facilitar tuning)
FUZZY_FULL_MATCH = 70
FUZZY_HALF_MATCH = 50
LEAKAGE_PER_WORD_MATCH = 80
LEAKAGE_GROUP_MATCH = 0.8
TIMING_TOLERANT_SEC = 1.0
TIMING_LENIENT_SEC = 2.5
TIMING_PENALTY_MID = 0.85
TIMING_PENALTY_FAR = 0.65
SANDWICH_THRESHOLD = 0.4
MAX_LEAKAGE_LOOKBACK = 6

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

def merge_vocal_fragments(transcribed_words):
    merged = []
    for w in transcribed_words:
        word = w["word"].lower().strip()
        is_fragment = word in VOCAL_FRAGMENTS or (len(word) <= 2 and re.match(r'^[aeiouáéíóúãõ]+$', word))
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


def calculate_score(expected_timed: list[dict], transcribed_words: list[dict], prev_expected_words: list[str] = None, language: str | None = None) -> dict:
    if not expected_timed:
        return {"score": 0, "details": "Nenhuma letra esperada."}

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

            if overlap_found > 0:
                leaked = [w['word'] for w in transcribed_words[:overlap_found]]
                logger.info(f"🛡️ [Perdão de Vazamento] {overlap_found} palavras vazadas do verso anterior: {leaked}")
                transcribed_words = transcribed_words[overlap_found:]

    # B. Merge de fragmentos vocálicos
    transcribed_words = merge_vocal_fragments(transcribed_words)

    # Tokenização e limpeza acústica normalizada
    expected_words = [clean_text(w["word"], language) for w in expected_timed]
    transcribed_clean = [{"word": clean_text(w["word"], language), "start": w["start"]} for w in transcribed_words]
    word_scores = []
    consumed_indices = set()

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

        if word_points > 0 and best_match_idx != -1:
            diff = abs(transcribed_clean[best_match_idx]["start"] - exp_word_data["expected_start"])
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
    final_score = (total_points / len(expected_words)) * 100
    
    return {
        "score": round(final_score, 1),
        "transcription": " ".join([w["word"] for w in transcribed_clean]),
        "matched_words": len(consumed_indices) + rescued_count,
        "total_expected": len(expected_words)
    }