import os
import sys
import json
import shutil
import argparse
import asyncio
import logging
import subprocess
from pathlib import Path
from pydub import AudioSegment
import numpy as np

# Configura o stdout para UTF-8 de forma robusta para evitar UnicodeEncodeError no console do Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configuração de Logging para a ferramenta CLI
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reinstall_song")

# Adiciona o diretório do projeto e o server ao path para os imports corretos
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "server"))

from state import ffmpeg_bin_dir
from utils.text import parse_time_to_seconds
from utils.youtube import download_youtube_audio
from tools.generate_lrc import generate_lrc
from tools.prepare_song import prepare_song

def _slice_with_padding(audio: AudioSegment, start_sec: float, end_sec: float, padding_sec: float) -> AudioSegment:
    """Corta o áudio e insere silêncio opcional no início (padding)."""
    duration_ms = len(audio)
    start_ms = max(0, int(start_sec * 1000))
    end_ms = int(end_sec * 1000) if end_sec > 0 else duration_ms
    end_ms = min(end_ms, duration_ms)
    sliced = audio[start_ms:end_ms]
    if padding_sec > 0:
        silence = AudioSegment.silent(duration=int(padding_sec * 1000), frame_rate=sliced.frame_rate)
        return silence + sliced
    return sliced

def _vocal_to_float32_mono_16k(vocal: AudioSegment) -> np.ndarray:
    """Resamplea vocal para 16kHz mono float32 normalizado, pronto para o Whisper."""
    WHISPER_SR = 16000
    resampled = vocal.set_frame_rate(WHISPER_SR).set_channels(1)
    raw = np.array(resampled.get_array_of_samples(), dtype=np.float32)
    if resampled.sample_width == 2:
        raw /= 32768.0
    elif resampled.sample_width == 4:
        raw /= 2147483648.0
    return raw

async def reinstall_song(song_dir_path: str, language: str = None) -> bool:
    song_dir = Path(song_dir_path)
    meta_path = song_dir / "meta.json"
    
    if not meta_path.exists():
        logger.error(f"Erro: Arquivo meta.json não foi encontrado em: {song_dir_path}")
        return False
        
    logger.info(f"--- Iniciando Reinstalação de Música: {song_dir.name} ---")
    
    # 1. Carrega os dados de metadados originais
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        logger.error(f"Erro ao carregar meta.json: {e}")
        return False
        
    def _get_field(sec: str, key: str, default=None):
        if isinstance(meta.get(sec), dict):
            val = meta[sec].get(key)
            if val is not None:
                return val
        return meta.get(key, default)

    # Extrai dados do YouTube e parâmetros de corte
    yt_vocal = _get_field("audio", "youtube_vocal_url")
    yt_backing = _get_field("audio", "youtube_backing_url")
    song_lang = language or _get_field("meta", "language") or "pt"
    
    vocal_start = _get_field("audio", "vocal_start", "0.0")
    vocal_end = _get_field("audio", "vocal_end", "-1.0")
    backing_start = _get_field("audio", "backing_start", "0.0")
    backing_end = _get_field("audio", "backing_end", "-1.0")
    silence_padding = _get_field("audio", "silence_padding", "0.0")
    lyrics_start = _get_field("lyrics", "lyrics_start", "0.0")
    plain_lyrics = _get_field("lyrics", "plain_lyrics")
    
    if not yt_vocal:
        logger.error("Erro: meta.json deve conter pelo menos 'youtube_vocal_url' (no campo 'audio') para reinstalação.")
        return False

    # 2. Backup de letras customizadas (LRC e TXT) para preservar as edições do usuário se necessário
    lrc_backup = None
    txt_backup = None
    lrc_file = song_dir / "lyrics.lrc"
    txt_file = song_dir / "lyrics.txt"
    
    if lrc_file.exists():
        logger.info("Fazendo backup temporário das letras sincronizadas (lyrics.lrc)...")
        lrc_backup = lrc_file.read_text(encoding="utf-8")
    if txt_file.exists():
        logger.info("Fazendo backup temporário das letras planas (lyrics.txt)...")
        txt_backup = txt_file.read_text(encoding="utf-8")

    # Se plain_lyrics não estiver no meta.json, mas tivermos um backup de lyrics.txt, usamos o backup!
    if (not plain_lyrics or not plain_lyrics.strip()) and txt_backup and txt_backup.strip():
        logger.info("plain_lyrics não encontrado no meta.json, mas backup de lyrics.txt está disponível. Utilizando para alinhamento!")
        plain_lyrics = txt_backup
        # Sincroniza de volta no meta.json para persistir
        if "lyrics" not in meta or not isinstance(meta["lyrics"], dict):
            meta["lyrics"] = {}
        meta["lyrics"]["plain_lyrics"] = plain_lyrics
        try:
            with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(meta, f, indent=4, ensure_ascii=False)
            logger.info("meta.json atualizado com plain_lyrics obtido do backup de lyrics.txt.")
        except Exception as e:
            logger.warning(f"Não foi possível salvar a atualização no meta.json: {e}")

    # 3. Limpeza total da pasta da música (exceto meta.json)
    logger.info("Limpando arquivos antigos da pasta...")
    for item in song_dir.iterdir():
        if item.name == "meta.json":
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            logger.warning(f"Não foi possível remover o arquivo residual {item.name}: {e}")

    # 4. Downloads frescos do YouTube (e separação opcional com Demucs)
    temp_vocal = song_dir / "temp_vocal.mp3"
    temp_backing = song_dir / "temp_backing.mp3"
    original_audio_path = song_dir / "original.mp3"
    demucs_out_dir = song_dir / "demucs_output"
    
    use_demucs = not yt_backing or not yt_backing.strip()
    
    try:
        if use_demucs:
            logger.info("Nenhuma URL de backing fornecida. Utilizando abordagem Demucs no áudio original!")
            logger.info(f"Baixando áudio original do YouTube: {yt_vocal}")
            success = await download_youtube_audio(yt_vocal, original_audio_path, ffmpeg_bin_dir)
            if not success or not original_audio_path.exists():
                logger.error("Erro crítico: Falha ao baixar o áudio original do YouTube.")
                return False
                
            # Localiza demucs.exe na pasta de binários do python
            python_dir = Path(sys.executable).parent
            demucs_exe = python_dir / "demucs.exe"
            if not demucs_exe.exists():
                demucs_exe = python_dir / "Scripts" / "demucs.exe"
            if not demucs_exe.exists():
                demucs_exe = "demucs"
                
            logger.info("Executando separação Demucs com aceleração de hardware CUDA...")
            demucs_cmd = [
                str(demucs_exe),
                "--two-stems", "vocals",
                "-d", "cuda",
                "-o", str(demucs_out_dir),
                str(original_audio_path)
            ]
            process = subprocess.run(demucs_cmd, capture_output=True, text=True)
            if process.returncode != 0:
                logger.error(f"Erro ao executar Demucs: {process.stderr}")
                return False
                
            separated_dir = demucs_out_dir / "htdemucs" / "original"
            vocals_wav = separated_dir / "vocals.wav"
            no_vocals_wav = separated_dir / "no_vocals.wav"
            
            if not vocals_wav.exists() or not no_vocals_wav.exists():
                logger.error("Erro crítico: Os arquivos separados pelo Demucs não foram gerados.")
                return False
                
            vocal_audio = AudioSegment.from_file(str(vocals_wav))
            backing_audio = AudioSegment.from_file(str(no_vocals_wav))
        else:
            logger.info("Baixando canais de áudio frescos do YouTube...")
            logger.info(f" -> Vocal: {yt_vocal}")
            logger.info(f" -> Instrumental: {yt_backing}")
            
            v_ok, b_ok = await asyncio.gather(
                download_youtube_audio(yt_vocal, temp_vocal, ffmpeg_bin_dir),
                download_youtube_audio(yt_backing, temp_backing, ffmpeg_bin_dir)
            )
            
            if not v_ok or not temp_vocal.exists():
                logger.error("Erro crítico: Falha ao baixar o canal Vocal do YouTube.")
                return False
            if not b_ok or not temp_backing.exists():
                logger.error("Erro crítico: Falha ao baixar o canal Instrumental do YouTube.")
                return False
                
            vocal_audio = AudioSegment.from_file(str(temp_vocal))
            backing_audio = AudioSegment.from_file(str(temp_backing))
            
        # 5. Processar, cortar e salvar os canais de áudio definitivos
        logger.info("Cortando e processando os arquivos de áudio...")
        force_vs = _get_field("audio", "force_vocal_start", False)
        v_start_sec = parse_time_to_seconds(vocal_start) if force_vs else 0.0
        v_end_sec = parse_time_to_seconds(vocal_end)
        b_start_sec = parse_time_to_seconds(backing_start) if force_vs else 0.0
        b_end_sec = parse_time_to_seconds(backing_end)
        padding_sec = max(0.0, parse_time_to_seconds(silence_padding))
        lyrics_start_val = parse_time_to_seconds(lyrics_start) if force_vs else 0.0
        
        # Processa Vocal
        processed_vocal = _slice_with_padding(vocal_audio, v_start_sec, v_end_sec, padding_sec)
        processed_vocal.export(str(song_dir / "vocal.mp3"), format="mp3")
        
        # Processa Instrumental
        processed_backing = _slice_with_padding(backing_audio, b_start_sec, b_end_sec, padding_sec)
        processed_backing.export(str(song_dir / "backing_track.mp3"), format="mp3")
        
        logger.info("Áudios cortados e exportados com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao processar/cortar áudios: {e}")
        return False
    finally:
        # Limpeza proativa de arquivos temporários e do Demucs
        for tmp in (temp_vocal, temp_backing, original_audio_path):
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
        if demucs_out_dir.exists():
            try:
                shutil.rmtree(demucs_out_dir)
            except Exception:
                pass

    # 6. Restauração das letras ou geração de nova se não houver backup
    if plain_lyrics and plain_lyrics.strip():
        # Se temos plain_lyrics no meta.json, recriamos o arquivo de letras txt e alinhamos com o Whisper!
        logger.info("plain_lyrics encontrado no meta.json. Recriando lyrics.txt e alinhando com Whisper...")
        txt_file.write_text(plain_lyrics.strip() + "\n", encoding="utf-8")
        
        try:
            from utils.lrc_align import align_plain_lyrics
            from stt_engine import get_stt_engine
            
            stt = get_stt_engine()
            raw_data = _vocal_to_float32_mono_16k(processed_vocal)
            segments, _info = stt.model.transcribe(
                raw_data,
                language=song_lang,
                beam_size=5,
                vad_filter=True,  # detecta onde a voz realmente começa
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
                word_timestamps=True,
            )
            segments_list = list(segments)
            total_duration = len(processed_vocal) / 1000.0
            
            lrc_text, fallback_used = align_plain_lyrics(
                plain_lyrics, segments_list, _get_field("meta", "title", ""), _get_field("meta", "artist", ""), lyrics_start_val, total_duration
            )
            lrc_file.write_text(lrc_text, encoding="utf-8")
            logger.info("Arquivo lyrics.lrc alinhado e gerado com sucesso a partir de plain_lyrics!")
        except Exception as e:
            logger.error(f"Erro ao alinhar plain_lyrics com Whisper: {e}")
            if lrc_backup is not None:
                logger.info("Tentando restaurar o backup das letras sincronizadas lyrics.lrc devido ao erro...")
                lrc_file.write_text(lrc_backup, encoding="utf-8")
                if txt_backup is not None:
                    txt_file.write_text(txt_backup, encoding="utf-8")
            else:
                logger.info("Tentando fallback de geração automática de LRC puro...")
                generate_lrc(str(song_dir), language=song_lang)
    elif lrc_backup is not None:
        logger.info("Restaurando backup de letras sincronizadas lyrics.lrc...")
        lrc_file.write_text(lrc_backup, encoding="utf-8")
        if txt_backup is not None:
            txt_file.write_text(txt_backup, encoding="utf-8")
    else:
        logger.info("Nenhuma letra disponível. Gerando nova transcrição com Whisper (generate_lrc)...")
        try:
            generate_lrc(str(song_dir), language=song_lang)
        except Exception as e:
            logger.error(f"Aviso: Erro ao transcrever letras com o Whisper: {e}")

    # 7. Rodar o alinhamento word-level (prepare_song)
    logger.info("Executando o alinhamento word-level (prepare_song)...")
    try:
        prepare_song(str(song_dir), language=song_lang)
        logger.info(f"[SUCCESS] Reinstalação de '{song_dir.name}' concluída com sucesso absoluto!")
        return True
    except Exception as e:
        logger.error(f"Erro ao alinhar canções no prepare_song: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Algoritmo de Reinstalação de Música via meta.json")
    parser.add_argument("song_dir", help="Caminho da pasta da música")
    parser.add_argument("--lang", default=None, help="Idioma da música (opcional, sobrescreve meta.json)")
    args = parser.parse_args()
    
    asyncio.run(reinstall_song(args.song_dir, args.lang))
