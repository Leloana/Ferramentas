import ollama
import time
from config import GENRE_ALIASES

class GenreClassifier:
    def __init__(self, model):
        self.model = model

    def classify(self, title, artist):
        prompt = f"""Você é um classificador de gênero musical.
Responda APENAS com uma palavra em português minúsculo (ex: rock, pop, sertanejo, rap, eletrônico, mpb, clássico, jazz, outros).
Música: "{title}" - Artista: "{artist}"
Gênero:"""
        try:
            response = ollama.chat(model=self.model, messages=[
                {
                    'role': 'user',
                    'content': prompt
                }
            ])
            genre_raw = response['message']['content'].strip().lower()
            
            # Limpar pontuações, caso o modelo retorne algo como "rock."
            import string
            genre_raw = genre_raw.translate(str.maketrans('', '', string.punctuation))
            
            # Pegar apenas a primeira palavra caso ele ignore a regra de uma palavra
            genre_raw = genre_raw.split()[0] if genre_raw else "outros"
            
            # Normalizar
            return GENRE_ALIASES.get(genre_raw, genre_raw)
        except Exception as e:
            print(f"Erro ao classificar '{title}': {e}")
            return "outros"

    def classify_tracks(self, tracks):
        classified_tracks = []
        for track in tracks:
            genre = self.classify(track['title'], track['artist'])
            track['genre'] = genre
            classified_tracks.append(track)
            time.sleep(0.5) # Rate limit
        return classified_tracks
