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
    
    # 1.1. Orquestra busca de letras na API (LRCLIB + fallback) se necessário ou para obter synced LRC
    fetched_plain_lyrics = None
    fetched_synced_lrc = None
    
    artist = _get_field("meta", "artist")
    title = _get_field("meta", "title")
    if artist and title:
        try:
            from utils.lyrics_fetcher import fetch_lyrics
            logger.info(f"Buscando letras na API para: {artist} - {title}")
            fetched = fetch_lyrics(artist, title)
            if fetched:
                fetched_plain_lyrics = fetched.get("plainLyrics")
                fetched_synced_lrc = fetched.get("syncedLyrics")
                logger.info(f"Letras da API encontradas. Synced LRC disponível: {bool(fetched_synced_lrc)}")
        except Exception as e:
            logger.warning(f"Erro ao buscar letras na API: {e}")
            
    # Se a música não tiver plain_lyrics no meta.json, mas encontramos na API, atualizamos no meta.json!
    if not plain_lyrics and fetched_plain_lyrics:
        logger.info("Adicionando letra plana encontrada via API ao meta.json...")
        plain_lyrics = normalize_lyrics_text(fetched_plain_lyrics)
        if "lyrics" not in meta or not isinstance(meta["lyrics"], dict):
            meta["lyrics"] = {}
        meta["lyrics"]["plain_lyrics"] = plain_lyrics
        try:
            with open(meta_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(meta, f, indent=4, ensure_ascii=False)
            logger.info("meta.json atualizado com plain_lyrics.")
        except Exception as e:
            logger.warning(f"Não foi possível salvar a atualização no meta.json: {e}")
            
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
    # Só restaura do txt se NÃO existe LRC — quando o LRC veio de API (LRCLIB), preservamos ele.
    if not plain_lyrics and txt_backup and txt_backup.strip() and lrc_backup is None:
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

    # Garante que o arquivo lyrics.txt local exista e esteja atualizado com o plain_lyrics do meta.json
    if plain_lyrics and plain_lyrics.strip():
        logger.info("Gerando/atualizando lyrics.txt com plain_lyrics do meta.json...")
        try:
            txt_file.write_text(plain_lyrics + "\n", encoding="utf-8")
        except Exception as e:
            logger.warning(f"Erro ao gravar lyrics.txt: {e}")

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
                process = await asyncio.to_thread(subprocess.run, demucs_cmd, capture_output=False, text=True)
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
                process = await asyncio.to_thread(subprocess.run, demucs_cmd, capture_output=False, text=True)
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
        # 1. Tenta usar o synced LRC obtido via API se align_lyrics=False
        if fetched_synced_lrc and not align_lyrics:
            logger.info("synced LRC obtido via API. Salvando como lyrics.lrc e pulando Whisper...")
            try:
                lrc_file.write_text(fetched_synced_lrc, encoding="utf-8")
                has_lrc = True
            except Exception as e:
                logger.error(f"Erro ao salvar synced LRC da API: {e}")
        # 2. Tenta restaurar o backup local se existia e align_lyrics=False
        elif lrc_backup is not None and not align_lyrics:
            logger.info("Restaurando backup local de letras sincronizadas (lyrics.lrc) já que align_lyrics=False...")
            try:
                lrc_file.write_text(lrc_backup, encoding="utf-8")
                has_lrc = True
            except Exception as e:
                logger.error(f"Erro ao restaurar backup de lyrics.lrc: {e}")
        # 3. Preserva LRC existente (ex: vindo de API LRCLIB) a menos que o
        # usuário tenha pedido explicitamente alinhamento forçado (PRO).
        elif lrc_file.exists() and not align_lyrics:
            logger.info("lyrics.lrc já existe e align_lyrics=False. Mantendo lyrics.lrc existente.")
            has_lrc = True
        elif plain_lyrics and plain_lyrics.strip() and align_lyrics:
            logger.info("plain_lyrics disponível e align_lyrics=True. Executando Forced Alignment (PRO) com MMS_FA...")
            try:
                from utils.lrc_pro import align_lyrics_forced
                import torch
                
                device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"Chamando Forced Alignment (PRO) no dispositivo: {device}")
                corrected_segments, lrc_text = await asyncio.to_thread(
                    align_lyrics_forced,
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
                    def transcribe_trans():
                        segments, _info = stt.model.transcribe(
                            raw_data,
                            language=song_lang,
                            initial_prompt=plain_lyrics if plain_lyrics else None,
                            **TRANSCRIBE_KWARGS,
                        )
                        return list(segments)
                    segments_list = await asyncio.to_thread(transcribe_trans)
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
                        await asyncio.to_thread(generate_lrc, str(song_dir), language=song_lang, debug=False)
                        has_lrc = True
        else:
            # Caso align_lyrics=False (FAST) ou plain_lyrics ausente
            logger.info("Executando transcrição direta com Whisper (FAST)...")
            try:
                await asyncio.to_thread(generate_lrc, str(song_dir), language=song_lang, debug=False)
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
            await asyncio.to_thread(generate_lrc, str(song_dir), language=song_lang, debug=False)
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
            await asyncio.to_thread(generate_lrc, str(song_dir), language=song_lang, debug=True)
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
        await asyncio.to_thread(prepare_song, str(song_dir), language=song_lang, debug=True)
        await asyncio.to_thread(prepare_song, str(song_dir), language=song_lang, debug=False)

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

# ---------------------------------------------------------------------------
# Helpers para delegação ao servidor HTTP (evita conflito de GPU)
# ---------------------------------------------------------------------------

SERVER_PORTS = [8000, 8001]  # Portas candidatas do servidor karaokê
_SERVER_BASE_URL: str | None = None  # Cache: porta detectada


def _detect_server_url() -> str | None:
    """Tenta detectar se o servidor está rodando e retorna a URL base."""
    import socket
    for port in SERVER_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1.0):
                return f"http://127.0.0.1:{port}"
        except OSError:
            pass
    return None


def _delegate_to_server(song_dir_path: str, align_lyrics: bool) -> bool:
    """Delega o reinstall para a API HTTP do servidor.

    O servidor já tem o modelo Whisper carregado como singleton e usa o
    ``whisper_lock`` para serializar o acesso à GPU — evitando o conflito
    que ocorre quando este script abre um segundo processo com outro modelo
    na VRAM enquanto o jogo está em curso.

    Retorna True se conseguiu delegar com sucesso, False caso contrário
    (servidor sem a rota, erro HTTP, etc.).
    """
    try:
        import urllib.request
        import urllib.error
    except ImportError:
        return False

    song_dir = Path(song_dir_path)
    song_id = song_dir.name  # A rota usa o slug (nome da pasta)

    global _SERVER_BASE_URL
    if _SERVER_BASE_URL is None:
        _SERVER_BASE_URL = _detect_server_url()
    if _SERVER_BASE_URL is None:
        return False

    align_param = "true" if align_lyrics else "false"
    url = f"{_SERVER_BASE_URL}/api/reinstall-song/{song_id}?align_lyrics={align_param}"

    logger.info(f"Servidor karaokê detectado em {_SERVER_BASE_URL}!")
    logger.info(f"Delegando reinstall para a API HTTP → {url}")
    logger.info("Aguardando conclusão... (o servidor usa o modelo Whisper já carregado na GPU)")

    try:
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Length", "0")
        with urllib.request.urlopen(req, timeout=1800) as resp:  # até 30 min
            import json as _json
            body = _json.loads(resp.read().decode("utf-8"))
        if body.get("success"):
            logger.info(f"[SUCCESS] API reportou sucesso: {body.get('message', 'ok')}")
            return True
        else:
            logger.error(f"API reportou falha: {body}")
            return False
    except urllib.error.HTTPError as e:
        logger.error(f"Erro HTTP da API: {e.code} {e.reason}")
        try:
            import json as _json
            err_body = _json.loads(e.read().decode("utf-8"))
            logger.error(f"Detalhe: {err_body.get('detail', '')}")
        except Exception:
            pass
        return False
    except Exception as e:
        logger.error(f"Erro ao chamar API do servidor: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Algoritmo de Reinstalação de Música via meta.json")
    parser.add_argument("song_dir", help="Caminho da pasta da música")
    parser.add_argument("--lang", default=None, help="Idioma da música (opcional, sobrescreve meta.json)")
    parser.add_argument("--align-lyrics", action="store_true", help="Alinha plain_lyrics com os tempos do Whisper (default: False)")
    parser.add_argument("--no-delegate", action="store_true", help="Desativa a delegação automática ao servidor (força execução local)")
    args = parser.parse_args()

    # Tenta delegar ao servidor se estiver rodando — evita conflito de GPU.
    # Use --no-delegate para forçar execução local (ex: servidor desligado).
    if not args.no_delegate:
        server_url = _detect_server_url()
        if server_url:
            logger.info("=" * 60)
            logger.info("ATENÇÃO: Servidor karaokê detectado rodando!")
            logger.info("Para evitar conflito de GPU (dois modelos Whisper na VRAM),")
            logger.info("o reinstall será delegado para a API HTTP do servidor.")
            logger.info("Use --no-delegate para forçar execução local.")
            logger.info("=" * 60)
            _SERVER_BASE_URL = server_url
            success = _delegate_to_server(args.song_dir, args.align_lyrics)
            if success:
                sys.exit(0)
            else:
                logger.warning("Delegação ao servidor falhou. Executando localmente...")
                logger.warning("AVISO: Isso pode causar conflito de GPU se o jogo estiver ativo!")
        else:
            logger.info("Servidor karaokê não detectado. Executando reinstall localmente.")

    asyncio.run(reinstall_song(args.song_dir, args.lang, align_lyrics=args.align_lyrics))
