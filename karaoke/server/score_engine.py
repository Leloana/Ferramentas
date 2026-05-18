import re
from rapidfuzz import fuzz

# Dicionário de Normalização Acústica para simplificar Contrações e Homófonos (Inglês e Português)
ACOUSTIC_NORMALIZATION = {
    # Contrações & Homófonos de Pronomes / Advérbio / Verbo (Inglês)
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
    
    # Homófonos acústicos comuns (Inglês)
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
    
    # Homófonos acústicos comuns (Português)
    "mas": "mais", "mais": "mais",
    "e": "eh", "é": "eh", "eh": "eh",
    "a": "ah", "há": "ah", "ah": "ah",
    "pra": "para", "para": "para",
    "te": "ti", "ti": "ti",
    "o": "oh", "oh": "oh"
}

def clean_text(text):
    """Remove pontuação, converte para lowercase e normaliza homófonos e contrações."""
    if not text:
        return ""
    # Converte para lowercase, strip e remove pontuação básica mantendo letras e números
    t = re.sub(r'[^\w\s\']', '', text).lower().strip()
    # Remove apóstrofos extras para contração limpa
    t_clean = re.sub(r'[^\w\s]', '', t)
    
    # Retorna o correspondente normalizado acusticamente (se houver)
    return ACOUSTIC_NORMALIZATION.get(t_clean, t_clean)

def calculate_score(expected_timed: list[dict], transcribed_words: list[dict], prev_expected_words: list[str] = None) -> dict:
    if not expected_timed:
        return {"score": 0, "details": "Nenhuma letra esperada."}

    # A. Detecção e Remoção de Vazamento (Perdão Inteligente)
    if prev_expected_words and transcribed_words:
        prev_clean = [clean_text(w) for w in prev_expected_words if w]
        trans_clean = [clean_text(w["word"]) for w in transcribed_words if w]
        
        max_overlap = min(len(prev_clean), len(trans_clean), 6)
        overlap_found = 0
        
        for k in range(max_overlap, 0, -1):
            prev_suffix = prev_clean[-k:]
            trans_prefix = trans_clean[:k]
            
            match_count = 0
            for idx in range(k):
                ratio = fuzz.token_sort_ratio(prev_suffix[idx], trans_prefix[idx])
                if ratio >= 80:
                    match_count += 1
            
            if match_count / k >= 0.8:
                overlap_found = k
                break
                
        if overlap_found > 0:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🛡️ [Perdão de Vazamento] Detectadas {overlap_found} palavras vazadas do verso anterior: {[w['word'] for w in transcribed_words[:overlap_found]]}. Expurgando do cálculo do verso atual.")
            transcribed_words = transcribed_words[overlap_found:]

    expected_words = [clean_text(w["word"]) for w in expected_timed]
    transcribed_clean = [{"word": clean_text(w["word"]), "start": w["start"]} for w in transcribed_words]

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
        if best_ratio >= 70:
            word_points = 1.0
            consumed_indices.add(best_match_idx)
        elif best_ratio >= 50:
            word_points = 0.5
            consumed_indices.add(best_match_idx)
            
        # Penalidade de timing mais tolerante
        if word_points > 0 and best_match_idx != -1:
            trans_start = transcribed_clean[best_match_idx]["start"]
            exp_start = exp_word_data["expected_start"]
            diff = abs(trans_start - exp_start)
            
            if diff < 1.0:
                pass # Sem penalidade
            elif diff <= 2.5:
                word_points *= 0.85 # Perde só 15%
            else:
                word_points *= 0.65 # Perde só 35%
        
        word_scores.append(word_points)

    # Sandwich Recovery expandido para janela de 2 palavras
    rescued_count = 0
    if len(word_scores) >= 3:
        for idx in range(1, len(word_scores) - 1):
            if word_scores[idx] < 0.4 and word_scores[idx - 1] >= 0.4 and word_scores[idx + 1] >= 0.4:
                word_scores[idx] = 1.0
                rescued_count += 1
        # Janela de 2 palavras erradas entre corretas
        for idx in range(1, len(word_scores) - 2):
            if (word_scores[idx] < 0.4 and word_scores[idx + 1] < 0.4
                    and word_scores[idx - 1] >= 0.4 and word_scores[idx + 2] >= 0.4):
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