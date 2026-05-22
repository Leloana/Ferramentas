import os
import sys
import json
import time
import unittest
from pathlib import Path

# Configura o stdout para UTF-8 (evita UnicodeEncodeError no console do Windows).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 1. Setup Python paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "server"))

# 2. Bootstrapping CUDA DLLs
print("=== Initializing CUDA Bootstrap ===")
import utils.cuda_bootstrap  # noqa: F401

# 3. Forçar importação imediata de torch e torchaudio
import torch
import torchaudio

from utils.lrc_pro import parse_and_normalize_lyrics, align_lyrics_forced
from tools.prepare_song import prepare_song

class TestEscoltaVagalumesPipeline(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.song_dir = PROJECT_ROOT / "server" / "songs" / "escolta-de-vagalumes-rick-renner"
        cls.meta_path = cls.song_dir / "meta.json"
        cls.vocal_path = cls.song_dir / "vocal.mp3"
        
        # Verify test preconditions
        if not cls.meta_path.exists():
            raise FileNotFoundError(f"meta.json not found at {cls.meta_path}")
        if not cls.vocal_path.exists():
            raise FileNotFoundError(f"vocal.mp3 not found at {cls.vocal_path}")
            
        with open(cls.meta_path, "r", encoding="utf-8") as f:
            cls.meta_data = json.load(f)
            
        cls.plain_lyrics = cls.meta_data["lyrics"]["plain_lyrics"]

    def test_01_cuda_availability(self):
        """Verifica se o CUDA está ativo no PyTorch."""
        print("\n--- Teste 01: Verificando CUDA no PyTorch ---")
        cuda_available = torch.cuda.is_available()
        print(f"CUDA is available: {cuda_available}")
        if cuda_available:
            device_name = torch.cuda.get_device_name(0)
            print(f"CUDA Device: {device_name}")
        self.assertTrue(cuda_available, "Erro: CUDA não está disponível para aceleração GPU!")

    def test_02_lyrics_normalization_hyphens(self):
        """Garante que a normalização das letras remove hífens e outros caracteres indesejados."""
        print("\n--- Teste 02: Validando Normalização de Letra (hífens/acentos) ---")
        lines, flat_words = parse_and_normalize_lyrics(self.plain_lyrics)
        
        # O teste deve conter palavras como "bem-te-vi"
        self.assertIn("bem-te-vi", self.plain_lyrics.lower())
        
        # E a palavra normalizada deve ser "bemtevi"
        self.assertIn("bemtevi", flat_words)
        
        # Garante que nenhum caractere como '-' ou pontuação sobrou nas palavras normalizadas
        for word in flat_words:
            self.assertRegex(word, r"^[a-z']+$", f"Palavra normalizada '{word}' contém caracteres inválidos!")
            self.assertNotIn("-", word, f"Palavra normalizada '{word}' ainda contém hífen!")
            
        print("Normalização validada com sucesso! Sem hífens ou caracteres especiais.")

    def test_03_mms_fa_tokenization(self):
        """Valida se o tokenizer MMS_FA aceita todas as palavras normalizadas sem erro."""
        print("\n--- Teste 03: Testando Tokenizador MMS_FA ---")
        lines, flat_words = parse_and_normalize_lyrics(self.plain_lyrics)
        
        bundle = torchaudio.pipelines.MMS_FA
        tokenizer = bundle.get_tokenizer()
        
        # Tenta tokenizar
        try:
            tokens = tokenizer(flat_words)
            print(f"Tokenização efetuada com sucesso! Total de palavras: {len(flat_words)}, Total de tokens: {len(tokens)}")
            
            # Garante que nenhum token seja 0 (CTC blank token), o que causaria erro no CTC Align
            for idx, token_list in enumerate(tokens):
                for tok in token_list:
                    self.assertNotEqual(tok, 0, f"Token zero (CTC blank index) encontrado para a palavra '{flat_words[idx]}'!")
        except Exception as e:
            self.fail(f"Erro na tokenização pelo MMS_FA: {e}")

    def test_04_forced_alignment_execution(self):
        """Verifica a execução de Forced Alignment em GPU (CUDA) e o tempo de execução."""
        print("\n--- Teste 04: Rodando Forced Alignment (PRO) via CUDA ---")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        start_time = time.time()
        try:
            corrected_segments, lrc_text = align_lyrics_forced(
                str(self.vocal_path),
                self.plain_lyrics,
                language="pt",
                device=device
            )
            elapsed = time.time() - start_time
            print(f"Forced Alignment concluído em: {elapsed:.2f}s no dispositivo {device}")
            
            # Validações básicas de saída
            self.assertTrue(len(corrected_segments) > 0, "Nenhum segmento gerado!")
            self.assertTrue(len(lrc_text) > 0, "LRC gerado está vazio!")
            
            # Verifica monotonicidade dos tempos de cantar
            for i, seg in enumerate(corrected_segments):
                self.assertTrue(seg["sing_start"] < seg["sing_end"], f"Segmento {seg['id']} possui sing_start >= sing_end!")
                if i > 0:
                    self.assertTrue(
                        seg["sing_start"] >= corrected_segments[i-1]["sing_end"] - 0.5,
                        f"Sobreposição excessiva detectada no segmento {seg['id']}!"
                    )
                
                # Verifica sub-palavras (lyrics_timed)
                for w in seg["lyrics_timed"]:
                    self.assertTrue(w["expected_start"] <= w["expected_end"], f"Palavra {w['word']} tem start > end!")
                    
            print(f"Forced Alignment validado com sucesso! Total de segmentos: {len(corrected_segments)}")
            
        except Exception as e:
            self.fail(f"Erro ao executar align_lyrics_forced em GPU: {e}")

    def test_05_prepare_song_integration(self):
        """Verifica que prepare_song roda sem erros no diretório do song."""
        print("\n--- Teste 05: Rodando prepare_song (Whisper-based alignment) ---")
        try:
            # Roda prepare_song em modo não-debug (gera o segments.json final)
            prepare_song(str(cls_dir := self.song_dir), language="pt", debug=False)
            
            segments_path = self.song_dir / "segments.json"
            self.assertTrue(segments_path.exists(), "O arquivo segments.json não foi gerado pelo prepare_song!")
            
            with open(segments_path, "r", encoding="utf-8") as f:
                segs = json.load(f)
            self.assertTrue(len(segs) > 0, "O arquivo segments.json está vazio!")
            print("prepare_song rodou e gerou segments.json com sucesso!")
        except Exception as e:
            self.fail(f"Erro durante a execução do prepare_song: {e}")

if __name__ == "__main__":
    unittest.main()
