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
from utils.whisper_params import TRANSCRIBE_KWARGS
from utils.youtube import download_youtube_audio
from tools.generate_lrc import generate_lrc
from tools.prepare_song import prepare_song

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

async def reinstall_song(song_dir_path: str, language: str = None, clean_existing: bool = True) -> bool:
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

    # Extrai dados do YouTube
    yt_vocal = _get_field("audio", "youtube_vocal_url")
    yt_backing = _get_field("audio", "youtube_backing_url")
    song_lang = language or _get_field("meta", "language") or "pt"
    plain_lyrics = _get_field("lyrics", "plain_lyrics")
    
    vocal_exists = (song_dir / "vocal.mp3").exists()
    backing_exists = (song_dir / "backing_track.mp3").exists()
    
    if not yt_vocal and not vocal_exists:
        logger.error("Erro: meta.json deve conter 'youtube_vocal_url' (no campo 'audio') ou vocal.mp3 local já deve existir.")
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
            logger.info("meta.json updated with plain_lyrics.")
        except Exception as e:
            logger.warning(f"Não foi possível salvar a atualização no meta.json: {e}")

    # 3. Limpeza total da pasta da música (exceto meta.json) se clean_existing for True
    if clean_existing:
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
    else:
        logger.info("clean_existing=False. Preservando arquivos existentes na pasta para reaproveitamento inteligente.")

    # 4. Downloads frescos do YouTube (e separação opcional com Demucs)
    temp_vocal = song_dir / "temp_vocal.mp3"
    temp_backing = song_dir / "temp_backing.mp3"
    original_audio_path = song_dir / "original.mp3"
    demucs_out_dir = song_dir / "demucs_output"
    
    use_demucs = not yt_backing or not yt_backing.strip()
    
    try:
        if not clean_existing and vocal_exists and backing_exists:
            logger.info("vocal.mp3 e backing_track.mp3 já existem. Pulando download e separação de áudio.")
            vocal_audio = AudioSegment.from_file(str(song_dir / "vocal.mp3"))
            backing_audio = AudioSegment.from_file(str(song_dir / "backing_track.mp3"))
        elif not clean_existing and vocal_exists:
            logger.info("vocal.mp3 já existe. Pulando download do vocal.")
            vocal_audio = AudioSegment.from_file(str(song_dir / "vocal.mp3"))
            if use_demucs and not backing_exists:
                logger.info("Executando Demucs no vocal.mp3 existente para separar o instrumental...")
                python_dir = Path(sys.executable).parent
                demucs_exe = python_dir / "demucs.exe"
                if not demucs_exe.exists():
                    demucs_exe = python_dir / "Scripts" / "demucs.exe"
                if not demucs_exe.exists():
                    demucs_exe = "demucs"
                
                demucs_cmd = [
                    str(demucs_exe),
                    "--two-stems", "vocals",
                    "-d", "cuda",
                    "-o", str(demucs_out_dir),
                    str(song_dir / "vocal.mp3")
                ]
                process = subprocess.run(demucs_cmd, capture_output=True, text=True)
                if process.returncode != 0:
                    logger.error(f"Erro ao executar Demucs: {process.stderr}")
                    return False
                    
                separated_dir = demucs_out_dir / "htdemucs" / "vocal"
                no_vocals_wav = separated_dir / "no_vocals.wav"
                if not no_vocals_wav.exists():
                    logger.error("Erro crítico: backing track não gerada pelo Demucs.")
                    return False
                    
                backing_audio = AudioSegment.from_file(str(no_vocals_wav))
                backing_audio.export(str(song_dir / "backing_track.mp3"), format="mp3")
            elif backing_exists:
                backing_audio = AudioSegment.from_file(str(song_dir / "backing_track.mp3"))
            else:
                # Fallback se não há backing track e use_demucs=False
                backing_audio = AudioSegment.silent(duration=1000)
        else:
            # 1 - Baixa áudio do YouTube
            if use_demucs:
                logger.info("Nenhuma URL de backing fornecida. Utilizando abordagem Demucs no áudio original!")
                logger.info(f"Baixando áudio original do YouTube: {yt_vocal}")
                success = await download_youtube_audio(yt_vocal, original_audio_path, ffmpeg_bin_dir)
                if not success or not original_audio_path.exists():
                    logger.error("Erro crítico: Falha ao baixar o áudio original do YouTube.")
                    return False
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

            # 2 - Cria arquivo lyrics.txt
            if plain_lyrics and plain_lyrics.strip():
                logger.info("Cria arquivo lyrics.txt a partir de plain_lyrics...")
                txt_file.write_text(plain_lyrics.strip() + "\n", encoding="utf-8")

            # 3 - Separa áudio do youtube backing e vocal (ou exporta canais já baixados)
            if use_demucs:
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
                vocal_audio = AudioSegment.from_file(str(temp_vocal))
                backing_audio = AudioSegment.from_file(str(temp_backing))
                
            # Salvar os canais de áudio definitivos sem corte/slicing
            logger.info("Salvando os canais de áudio definitivos...")
            vocal_audio.export(str(song_dir / "vocal.mp3"), format="mp3")
            backing_audio.export(str(song_dir / "backing_track.mp3"), format="mp3")
            logger.info("Áudios exportados com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao processar áudios: {e}")
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

    # 4 - whisper percorre o arquivo vocal fazendo os tempos & 5 - Cria arquivo lyrics.lrc
    if lrc_file.exists() and (not plain_lyrics or not plain_lyrics.strip()):
        logger.info("lyrics.lrc já existe e plain_lyrics não foi fornecido. Mantendo lyrics.lrc existente.")
    elif plain_lyrics and plain_lyrics.strip():
        logger.info("plain_lyrics disponível. Whisper percorrendo arquivo vocal para cruzar com lyrics.txt...")
        
        try:
            from utils.lrc_align import align_plain_lyrics
            from stt_engine import get_stt_engine
            
            stt = get_stt_engine()
            raw_data = _vocal_to_float32_mono_16k(vocal_audio)
            # Mesmos parâmetros do path de upload — antes divergiam (upload usava defaults
            # do faster-whisper e reinstall usava min_silence=2000ms agressivo), o que
            # produzia LRC diferente dependendo de qual caminho gerou. Ver
            # `utils/whisper_params.py` para a tabela de tuning.
            segments, _info = stt.model.transcribe(
                raw_data,
                language=song_lang,
                initial_prompt=plain_lyrics if plain_lyrics else None,
                **TRANSCRIBE_KWARGS,
            )
            segments_list = list(segments)
            total_duration = len(vocal_audio) / 1000.0
            lrc_text, fallback_used = align_plain_lyrics(
                plain_lyrics, segments_list, _get_field("meta", "title", ""), _get_field("meta", "artist", ""), total_duration
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
