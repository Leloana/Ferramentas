import argparse
import asyncio
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from pydub import AudioSegment

# Configura o stdout para UTF-8 (evita UnicodeEncodeError no console do Windows).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reinstall_song")

# Adiciona o diretório do projeto e o server ao path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "server"))

# Limpa PATH e registra DLLs do CUDA antes de qualquer importação de ML
import utils.cuda_bootstrap  # noqa: F401
import torch  # noqa: F401 (Força carregamento de DLLs do PyTorch/cuDNN primeiro)
import torchaudio  # noqa: F401

from state import ffmpeg_bin_dir
from utils.audio import vocal_to_float32_mono_16k
from utils.meta import get_meta_field
from utils.text import normalize_lyrics_text
from utils.whisper_params import TRANSCRIBE_KWARGS
from utils.youtube import download_youtube_audio
from tools.generate_lrc import generate_lrc
from tools.prepare_song import prepare_song


async def reinstall_song(
    song_dir_path: str,
    language: str = None,
    clean_existing: bool = True,
    skip_prepare_song: bool = False,
    align_lyrics: bool = False,
) -> bool:
    """Pipeline completo: download → Demucs → Whisper → LRC → prepare_song.

    Se `skip_prepare_song=True`, pula a última etapa (alinhamento word-level
    que gera `segments.json`). Útil quando o LRC ainda precisa ser aprovado
    pelo usuário antes de finalizar — o `segments.json` é regerado depois,
    no `save_lyrics`, sobre o LRC corrigido.
    """
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
        return get_meta_field(meta, sec, key, default)

    # Extrai dados do YouTube
    yt_vocal = _get_field("audio", "youtube_vocal_url")
    yt_backing = _get_field("audio", "youtube_backing_url")
    song_lang = language or _get_field("meta", "language") or "pt"
    # Normaliza ao ler: meta.json antigo pode ter sido salvo com `\r\n` do Windows,
    # o que gera `^M` e linhas duplicadas no lyrics.txt depois.
    plain_lyrics = normalize_lyrics_text(_get_field("lyrics", "plain_lyrics"))
    
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
        txt_backup = normalize_lyrics_text(txt_file.read_text(encoding="utf-8"))

    # Se plain_lyrics não estiver no meta.json, mas tivermos um backup de lyrics.txt, usamos o backup!
    if not plain_lyrics and txt_backup and txt_backup.strip():
        logger.info("plain_lyrics não encontrado no meta.json, mas backup de lyrics.txt está disponível. Utilizando para alinhamento!")
        plain_lyrics = normalize_lyrics_text(txt_backup)
        # Sincroniza de volta no meta.json para persistir (já normalizado)
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
                
                device = "cpu"
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                except Exception:
                    pass

                demucs_cmd = [
                    str(demucs_exe),
                    "--two-stems", "vocals",
                    "-d", device,
                    "-o", str(demucs_out_dir),
                    str(song_dir / "vocal.mp3")
                ]
                process = subprocess.run(demucs_cmd, capture_output=False, text=True)
                if process.returncode != 0:
                    logger.info(f"Demucs exe: {demucs_exe}")
                    logger.info(f"Demucs cmd: {demucs_cmd}")
                    logger.info(f"Original audio exists: {original_audio_path.exists()}")
                    return False
                    
                separated_dir = demucs_out_dir / "htdemucs" / "vocal"
                no_vocals_wav = separated_dir / "no_vocals.wav"
                if not no_vocals_wav.exists():
                    logger.exception("Erro crítico: backing track não gerada pelo Demucs.")
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

            # 2 - Cria arquivo lyrics.txt (plain_lyrics já foi normalizado no read).
            if plain_lyrics:
                logger.info("Cria arquivo lyrics.txt a partir de plain_lyrics...")
                txt_file.write_text(plain_lyrics + "\n", encoding="utf-8")

            # 3 - Separa áudio do youtube backing e vocal (ou exporta canais já baixados)
            if use_demucs:
                python_dir = Path(sys.executable).parent
                demucs_exe = python_dir / "demucs.exe"
                if not demucs_exe.exists():
                    demucs_exe = python_dir / "Scripts" / "demucs.exe"
                if not demucs_exe.exists():
                    demucs_exe = "demucs"
                    
                device = "cpu"
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                except Exception:
                    pass

                logger.info(f"Executando separação Demucs no dispositivo: {device}")
                demucs_cmd = [
                    str(demucs_exe),
                    "--two-stems", "vocals",
                    "-d", device,
                    "-o", str(demucs_out_dir),
                    str(original_audio_path)
                ]
                process = subprocess.run(demucs_cmd, capture_output=False, text=True)
                if process.returncode != 0:
                    logger.info(f"Demucs exe: {demucs_exe}")
                    logger.info(f"Demucs cmd: {demucs_cmd}")
                    logger.info(f"Original audio exists: {original_audio_path.exists()}")
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
    has_lrc = False
    
    # Verifica se existe um backup premium/pro desta música para evitar perder alinhamentos lentos/manuais
    backup_dir = PROJECT_ROOT / "server" / "songs_backup" / song_dir.name
    backup_lrc = backup_dir / "lyrics.lrc"
    backup_segs = backup_dir / "segments.json"
    backup_txt = backup_dir / "lyrics.txt"
    
    if backup_lrc.exists() and backup_segs.exists():
        logger.info(f"Backup premium/pro encontrado em {backup_dir}. Restaurando lyrics.lrc e segments.json...")
        try:
            shutil.copy(str(backup_lrc), str(lrc_file))
            shutil.copy(str(backup_segs), str(song_dir / "segments.json"))
            if backup_txt.exists():
                shutil.copy(str(backup_txt), str(txt_file))
            has_lrc = True
            skip_prepare_song = True
            logger.info("Restauração do backup premium/pro concluída com sucesso!")
        except Exception as e:
            logger.error(f"Erro ao restaurar backup premium: {e}")
            
    if not has_lrc:
        if lrc_file.exists() and (not plain_lyrics or not plain_lyrics.strip()):
            logger.info("lyrics.lrc já existe e plain_lyrics não foi fornecido. Mantendo lyrics.lrc existente.")
            has_lrc = True
        elif plain_lyrics and plain_lyrics.strip() and align_lyrics:
            logger.info("plain_lyrics disponível e align_lyrics=True. Executando Forced Alignment (PRO) com MMS_FA...")
            try:
                from utils.lrc_pro import align_lyrics_forced
                import torch
                
                device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"Chamando Forced Alignment (PRO) no dispositivo: {device}")
                corrected_segments, lrc_text = align_lyrics_forced(
                    str(song_dir / "vocal.mp3"),
                    plain_lyrics,
                    language=song_lang,
                    device=device
                )
                
                # Salva o lyrics.lrc
                lrc_file.write_text(lrc_text, encoding="utf-8")
                
                # Salva o segments.json
                segments_path = song_dir / "segments.json"
                with open(segments_path, "w", encoding="utf-8") as f:
                    json.dump(corrected_segments, f, indent=2, ensure_ascii=False)
                
                has_lrc = True
                skip_prepare_song = True  # Já gerou o segments.json completo e com alinhamento perfeito!
                logger.info("Arquivo lyrics.lrc e segments.json gerados com sucesso via Forced Alignment (PRO)!")
            except Exception as e:
                logger.error(f"Erro ao executar Forced Alignment (PRO) com MMS_FA: {e}")
                logger.info("Tentando fallback de alinhamento com Whisper (lrc_align)...")
                try:
                    from utils.lrc_align import align_plain_lyrics
                    from stt_engine import get_stt_engine
                    
                    stt = get_stt_engine()
                    raw_data = vocal_to_float32_mono_16k(vocal_audio)
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
                    logger.info("Arquivo lyrics.lrc alinhado e gerado com sucesso via Whisper lrc_align!")
                    has_lrc = True
                except Exception as ex:
                    logger.error(f"Erro no fallback do lrc_align: {ex}")
                    if lrc_backup is not None:
                        logger.info("Restaurando backup de letras sincronizadas lyrics.lrc devido ao erro...")
                        lrc_file.write_text(lrc_backup, encoding="utf-8")
                        if txt_backup is not None:
                            txt_file.write_text(txt_backup, encoding="utf-8")
                        has_lrc = True
                    else:
                        logger.info("Tentando fallback de geração automática de LRC puro...")
                        generate_lrc(str(song_dir), language=song_lang, debug=False)
                        has_lrc = True
        else:
            # Caso align_lyrics=False (FAST) ou plain_lyrics ausente
            logger.info("Executando transcrição direta com Whisper (FAST)...")
            try:
                generate_lrc(str(song_dir), language=song_lang, debug=False)
                has_lrc = True
            except Exception as e:
                logger.error(f"Erro ao gerar transcrição FAST com Whisper: {e}")
                if lrc_backup is not None:
                    logger.info("Restaurando backup de letras sincronizadas lyrics.lrc devido ao erro...")
                    lrc_file.write_text(lrc_backup, encoding="utf-8")
                    if txt_backup is not None:
                        txt_file.write_text(txt_backup, encoding="utf-8")
                    has_lrc = True

    
    # Se não geramos lyrics.lrc (ou se align_lyrics=False)
    if not has_lrc:
        if plain_lyrics and plain_lyrics.strip():
            logger.info("Gerando resultado do Whisper direto para lyrics.lrc (alinhamento desativado via align_lyrics=False)...")
        else:
            logger.info("Nenhuma letra disponível ou plain_lyrics ausente. Gerando resultado do Whisper direto para lyrics.lrc...")
        try:
            generate_lrc(str(song_dir), language=song_lang, debug=False)
        except Exception as e:
            logger.error(f"Erro ao gerar transcrição direto com o Whisper: {e}")
            if lrc_backup is not None:
                logger.info("Restaurando backup de letras sincronizadas lyrics.lrc devido ao erro...")
                lrc_file.write_text(lrc_backup, encoding="utf-8")
                if txt_backup is not None:
                    txt_file.write_text(txt_backup, encoding="utf-8")
    else:
        # Se já alinhamos, opcionalmente geramos a versão debug pura como referência secundária
        logger.info("Gerando versão de referência de transcrição pura com Whisper (lyrics_debug.lrc)...")
        try:
            generate_lrc(str(song_dir), language=song_lang, debug=True)
        except Exception as e:
            logger.error(f"Aviso: Erro ao gerar transcrição de debug com o Whisper: {e}")

    # 7. Rodar o alinhamento word-level (prepare_song)
    # Quando `skip_prepare_song=True` (ex: upload aguardando aprovação do
    # usuário no editor), pula esta etapa — o segments.json será regerado
    # depois, no save_lyrics, sobre o LRC corrigido pelo usuário.
    if skip_prepare_song:
        logger.info("skip_prepare_song=True. Pulando alinhamento word-level (será feito no save-lyrics).")
        logger.info(f"[SUCCESS] Áudio + LRC preparados para '{song_dir.name}'.")
        return True

    logger.info("Executando o alinhamento word-level (prepare_song)...")
    try:
        prepare_song(str(song_dir), language=song_lang, debug=True)
        prepare_song(str(song_dir), language=song_lang, debug=False)

        # Realinhamento de segmentos e LRC pós-processamento
        if align_lyrics and txt_file.exists():
            plain_lyrics_content = txt_file.read_text(encoding="utf-8")
            from utils.lrc_realign import realign_segments
            
            # Corrige a versão debug se existir
            debug_segments_path = song_dir / "segments_debug.json"
            if debug_segments_path.exists():
                logger.info("Realinhando segmentos debug...")
                try:
                    with open(debug_segments_path, "r", encoding="utf-8") as f:
                        debug_segs = json.load(f)
                    corrected_debug_segs, debug_lrc = realign_segments(debug_segs, plain_lyrics_content)
                    with open(debug_segments_path, "w", encoding="utf-8") as f:
                        json.dump(corrected_debug_segs, f, indent=2, ensure_ascii=False)
                    (song_dir / "lyrics_debug_2.lrc").write_text(debug_lrc, encoding="utf-8")
                except Exception as e:
                    logger.warning(f"Erro ao realinhar versão debug: {e}")
                    
            # Corrige a versão principal
            main_segments_path = song_dir / "segments.json"
            if main_segments_path.exists():
                logger.info("Realinhando segmentos principais...")
                try:
                    with open(main_segments_path, "r", encoding="utf-8") as f:
                        main_segs = json.load(f)
                    corrected_main_segs, main_lrc = realign_segments(main_segs, plain_lyrics_content)
                    with open(main_segments_path, "w", encoding="utf-8") as f:
                        json.dump(corrected_main_segs, f, indent=2, ensure_ascii=False)
                    lrc_file.write_text(main_lrc, encoding="utf-8")
                    logger.info("Realinhamento concluído com sucesso!")
                except Exception as e:
                    logger.warning(f"Erro ao realinhar versão principal: {e}")

        logger.info(f"[SUCCESS] Reinstalação de '{song_dir.name}' concluída com sucesso absoluto!")
        return True
    except Exception as e:
        logger.error(f"Erro ao alinhar canções no prepare_song: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Algoritmo de Reinstalação de Música via meta.json")
    parser.add_argument("song_dir", help="Caminho da pasta da música")
    parser.add_argument("--lang", default=None, help="Idioma da música (opcional, sobrescreve meta.json)")
    parser.add_argument("--align-lyrics", action="store_true", help="Alinha plain_lyrics com os tempos do Whisper (default: False)")
    args = parser.parse_args()
    
    asyncio.run(reinstall_song(args.song_dir, args.lang, align_lyrics=args.align_lyrics))
