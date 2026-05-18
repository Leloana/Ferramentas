import asyncio
import json
import logging
import shutil
import socket
import sys
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Garante que a pasta server está no path do Python para localizador de módulos
server_dir = str(Path(__file__).parent.absolute())
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from utils.ffmpeg_bootstrap import bootstrap as _bootstrap_ffmpeg
ffmpeg_bin_dir = _bootstrap_ffmpeg()

from pydub import AudioSegment  # noqa: E402  (precisa vir após bootstrap do ffmpeg)

from state import song_manager
from utils.text import parse_time_to_seconds, slugify
from utils.youtube import download_youtube_audio
from ws.room import router as ws_router

# Configurações
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Karaoke MVP Server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas HTTP
CLIENT_DIR = Path(__file__).parent.parent / "client"
app.mount("/styles", StaticFiles(directory=str(CLIENT_DIR / "styles")), name="styles")
app.mount("/js", StaticFiles(directory=str(CLIENT_DIR / "js")), name="js")


def _no_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


@app.get("/")
async def get_index(response: Response):
    _no_cache(response)
    return FileResponse(CLIENT_DIR / "index.html")


@app.get("/songs")
@app.get("/api/songs")
async def list_songs(response: Response):
    _no_cache(response)
    return song_manager.list_songs()


@app.get("/songs/{song_id}/audio")
async def get_audio(song_id: str):
    audio_path = song_manager.get_audio_path(song_id)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Música não encontrada")
    return FileResponse(audio_path)


app.include_router(ws_router)


@app.post("/api/upload-song")
async def upload_song(
    title: str = Form(...),
    artist: str = Form(...),
    language: str = Form("en"),
    vocal_file: Optional[UploadFile] = File(None),
    backing_file: Optional[UploadFile] = File(None),
    lrc_file: Optional[UploadFile] = File(None),
    vocal_start: str = Form("0.0"),
    vocal_end: str = Form("-1.0"),
    backing_start: str = Form("0.0"),
    backing_end: str = Form("-1.0"),
    silence_padding: str = Form("0.0"),
    lyrics_start: str = Form("0.0"),
    youtube_vocal_url: Optional[str] = Form(None),
    youtube_backing_url: Optional[str] = Form(None),
    plain_lyrics: Optional[str] = Form(None)
):
    try:
        fallback_used = False
        slug = slugify(f"{title}-{artist}")
        songs_dir = Path(__file__).parent / "songs"
        song_dir = songs_dir / slug
        song_dir.mkdir(parents=True, exist_ok=True)
        
        # Salva todos os parâmetros de criação em um arquivo meta.json
        meta_data = {
            "title": title,
            "artist": artist,
            "language": language,
            "vocal_start": vocal_start,
            "vocal_end": vocal_end,
            "backing_start": backing_start,
            "backing_end": backing_end,
            "silence_padding": silence_padding,
            "lyrics_start": lyrics_start,
            "youtube_vocal_url": youtube_vocal_url,
            "youtube_backing_url": youtube_backing_url,
            "has_vocal_file": vocal_file is not None and vocal_file.filename != "",
            "has_backing_file": backing_file is not None and backing_file.filename != "",
            "has_lrc_file": lrc_file is not None and lrc_file.filename != ""
        }
        meta_path = song_dir / "meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=4, ensure_ascii=False)
        
        # Converte tempos flexíveis para segundos decimais reais
        v_start_val = parse_time_to_seconds(vocal_start)
        v_end_val = parse_time_to_seconds(vocal_end)
        b_start_val = parse_time_to_seconds(backing_start)
        b_end_val = parse_time_to_seconds(backing_end)
        s_padding_val = max(0.0, parse_time_to_seconds(silence_padding))
        lyrics_start_val = parse_time_to_seconds(lyrics_start)
        
        # Arquivos temporários para processamento pydub
        temp_vocal_path = song_dir / "temp_vocal.mp3"
        temp_backing_path = song_dir / "temp_backing.mp3"
        
        has_yt_vocal = youtube_vocal_url and youtube_vocal_url.strip()
        has_yt_backing = youtube_backing_url and youtube_backing_url.strip()
        
        if has_yt_vocal or has_yt_backing:
            if not has_yt_vocal or not has_yt_backing:
                raise HTTPException(
                    status_code=400, 
                    detail="Para importar do YouTube, você deve fornecer ambos os links: Vocal e Instrumental."
                )
                
            logger.info(f"Iniciando download duplo do YouTube:")
            logger.info(f"Vocal URL: {youtube_vocal_url}")
            logger.info(f"Instrumental URL: {youtube_backing_url}")
            
            # Downloads em paralelo de alta velocidade usando asyncio.gather
            v_task = download_youtube_audio(youtube_vocal_url.strip(), temp_vocal_path, ffmpeg_bin_dir)
            b_task = download_youtube_audio(youtube_backing_url.strip(), temp_backing_path, ffmpeg_bin_dir)
            
            v_success, b_success = await asyncio.gather(v_task, b_task)
            
            if not v_success or not temp_vocal_path.exists():
                raise HTTPException(status_code=400, detail="Falha ao baixar o áudio Vocal do YouTube. Verifique a URL.")
            if not b_success or not temp_backing_path.exists():
                raise HTTPException(status_code=400, detail="Falha ao baixar o áudio Instrumental do YouTube. Verifique a URL.")
        else:
            if not vocal_file or not backing_file:
                raise HTTPException(status_code=400, detail="Você precisa subir os arquivos locais de áudio ou fornecer ambos os links do YouTube.")
                
            with open(temp_vocal_path, "wb") as buffer:
                shutil.copyfileobj(vocal_file.file, buffer)
                
            with open(temp_backing_path, "wb") as buffer:
                shutil.copyfileobj(backing_file.file, buffer)
            
        # 1. Processamento de áudio do Vocal (Corte & Silêncio)
        vocal_segment = AudioSegment.from_file(str(temp_vocal_path))
        vocal_duration_ms = len(vocal_segment)
        v_start_ms = max(0, int(v_start_val * 1000))
        v_end_ms = int(v_end_val * 1000) if v_end_val > 0 else vocal_duration_ms
        v_end_ms = min(v_end_ms, vocal_duration_ms)
        sliced_vocal = vocal_segment[v_start_ms:v_end_ms]
        
        if s_padding_val > 0:
            silence_ms = int(s_padding_val * 1000)
            silence_segment = AudioSegment.silent(duration=silence_ms, frame_rate=sliced_vocal.frame_rate)
            final_vocal = silence_segment + sliced_vocal
        else:
            final_vocal = sliced_vocal
            
        final_vocal_path = song_dir / "vocal.mp3"
        final_vocal.export(str(final_vocal_path), format="mp3")
        
        # 2. Processamento de áudio do Instrumental (Corte & Silêncio)
        backing_segment = AudioSegment.from_file(str(temp_backing_path))
        backing_duration_ms = len(backing_segment)
        b_start_ms = max(0, int(b_start_val * 1000))
        b_end_ms = int(b_end_val * 1000) if b_end_val > 0 else backing_duration_ms
        b_end_ms = min(b_end_ms, backing_duration_ms)
        sliced_backing = backing_segment[b_start_ms:b_end_ms]
        
        if s_padding_val > 0:
            silence_ms = int(s_padding_val * 1000)
            silence_segment = AudioSegment.silent(duration=silence_ms, frame_rate=sliced_backing.frame_rate)
            final_backing = silence_segment + sliced_backing
        else:
            final_backing = sliced_backing
            
        final_backing_path = song_dir / "backing_track.mp3"
        final_backing.export(str(final_backing_path), format="mp3")
        
        # Limpar arquivos temporários
        if temp_vocal_path.exists():
            temp_vocal_path.unlink()
        if temp_backing_path.exists():
            temp_backing_path.unlink()
 
        # 3. Gerenciamento do arquivo LRC de letras
        has_lrc_uploaded = lrc_file is not None and lrc_file.filename != ""
        
        if has_lrc_uploaded:
            lrc_path = song_dir / "lyrics.lrc"
            lrc_content = await lrc_file.read()
            try:
                lrc_text = lrc_content.decode("utf-8")
            except UnicodeDecodeError:
                lrc_text = lrc_content.decode("latin-1")
            
            clean_lines = [line.strip() for line in lrc_text.splitlines() if line.strip()]
            clean_lyrics = "\n".join(clean_lines)
            
            with open(lrc_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(clean_lyrics)
                
            # Dispara o prepare_song imediatamente
            sys.path.append(str(Path(__file__).parent.parent / "tools"))
            from prepare_song import prepare_song
            prepare_song(str(song_dir), language)
            
            return {"success": True, "lyrics_status": "ready", "slug": slug, "fallback_used": fallback_used}
            
        else:
            # Caso não tenha LRC, transcreve com o Whisper e gera rascunho de LRC
            logger.info("Nenhum arquivo LRC enviado. Transcrevendo vocais recortados com o Whisper...")
            stt = get_stt_engine()
            
            # Resamplea para 16kHz Mono Float32 usando pydub diretamente na memória
            resampled_vocal = final_vocal.set_frame_rate(16000).set_channels(1)
            raw_data = np.array(resampled_vocal.get_array_of_samples(), dtype=np.float32)
            
            # Normalização de bits para float32
            if resampled_vocal.sample_width == 2:
                raw_data = raw_data / 32768.0
            elif resampled_vocal.sample_width == 4:
                raw_data = raw_data / 2147483648.0
                
            # Transcrição via faster-whisper com VAD desativado, sem condicionamento de contexto anterior e com carimbos de tempo por palavra para precisão cirúrgica
            segments, _ = stt.model.transcribe(
                raw_data, 
                language=language, 
                beam_size=5, 
                vad_filter=False,
                condition_on_previous_text=False,
                word_timestamps=True
            )
            segments_list = list(segments)
            
            if plain_lyrics and plain_lyrics.strip():
                logger.info("Letra de referência fornecida pelo usuário. Alinhando com a transcrição do Whisper...")
                import difflib
                
                # Salva o texto da letra original copiada e colada em lyrics.txt conforme solicitado sem linhas em branco extras e com EOL Unix
                txt_path = song_dir / "lyrics.txt"
                clean_txt_lines = [line.strip() for line in plain_lyrics.splitlines() if line.strip()]
                with open(txt_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(clean_txt_lines) + "\n")
                
                # 1. Parse da letra fornecida
                ref_lines = []
                for line in plain_lyrics.splitlines():
                    line_strip = line.strip()
                    if line_strip:
                        if line_strip.startswith("[") and "]" in line_strip:
                            continue
                        ref_lines.append(line_strip)
                
                lrc_lines = [
                    f"[ti:{title}]",
                    f"[ar:{artist}]",
                    ""
                ]
                
                if ref_lines:
                    # 2. Obter segmentos do Whisper com tempo de início e fim
                    whisper_lines = []
                    for seg in segments_list:
                        whisper_lines.append({
                            "start": seg.start,
                            "end": seg.end,
                            "text": seg.text.strip()
                        })
                        
                    if not whisper_lines:
                        # Fallback simples
                        last_t = lyrics_start_val
                        for i, ref in enumerate(ref_lines):
                            t = last_t + i * 4.0
                            m = int(t // 60)
                            s = int(t % 60)
                            ms = int((t % 1) * 100)
                            lrc_lines.append(f"[{m:02d}:{s:02d}.{ms:02d}]{ref}")
                    else:
                        def check_substring_match(ref_line, whisper_text):
                            ref_words = re.findall(r'\b\w+\b', ref_line.lower())
                            whisper_words = re.findall(r'\b\w+\b', whisper_text.lower())
                            if not ref_words or not whisper_words:
                                return 0.0
                            matches = 0
                            last_idx = -1
                            for w in ref_words:
                                try:
                                    idx = whisper_words.index(w, last_idx + 1)
                                    matches += 1
                                    last_idx = idx
                                except ValueError:
                                    pass
                            return matches / len(ref_words)
                            
                        n = len(ref_lines)
                        m = len(whisper_lines)
                        aligned_timestamps = [None] * n
                        if n > 0:
                            aligned_timestamps[0] = lyrics_start_val
                        segment_to_ref_lines = {}
                        
                        last_j = 0
                        matched_count = 0
                        for i in range(n):
                            best_j = -1
                            best_match_ratio = 0.0
                            search_start = last_j
                            search_end = min(m, last_j + 12)
                            
                            for j in range(search_start, search_end):
                                ratio = check_substring_match(ref_lines[i], whisper_lines[j]["text"])
                                if ratio > best_match_ratio:
                                    best_match_ratio = ratio
                                    best_j = j
                                    
                            if best_j != -1 and best_match_ratio >= 0.70:
                                aligned_timestamps[i] = whisper_lines[best_j]["start"]
                                last_j = best_j
                                matched_count += 1
                                if best_j not in segment_to_ref_lines:
                                    segment_to_ref_lines[best_j] = []
                                segment_to_ref_lines[best_j].append(i)
                                
                        # Distribui os tempos proporcionalmente dentro de cada segmento do Whisper
                        for j, indices in segment_to_ref_lines.items():
                            k = len(indices)
                            if k > 1:
                                seg_start = whisper_lines[j]["start"]
                                seg_end = whisper_lines[j]["end"]
                                duration = seg_end - seg_start
                                for idx, ref_idx in enumerate(indices):
                                    aligned_timestamps[ref_idx] = seg_start + idx * (duration / k)
                                    
                        # Se tivemos pouquíssimos matches (menos de 15% das linhas ou 3 linhas), usa distribuição temporal linear robusta
                        total_duration = len(final_vocal) / 1000.0
                        min_matches_needed = max(3, int(n * 0.15))
                        
                        if matched_count < min_matches_needed:
                            logger.info(f"Poucos matches com o Whisper ({matched_count}/{n}). Usando distribuição temporal linear robusta.")
                            fallback_used = True
                            start_t = lyrics_start_val
                            end_t = max(start_t + 10.0, total_duration - 5.0)
                            step = (end_t - start_t) / max(1, n - 1)
                            for i in range(n):
                                aligned_timestamps[i] = start_t + i * step
                        else:
                            # Interpolação normal para preencher os Nones se restarem
                            last_t = lyrics_start_val
                            for i in range(n):
                                if aligned_timestamps[i] is None:
                                    next_t = None
                                    for k in range(i + 1, n):
                                        if aligned_timestamps[k] is not None:
                                            next_t = aligned_timestamps[k]
                                            break
                                    if next_t is not None:
                                        steps = (k - i) + 1
                                        aligned_timestamps[i] = last_t + (next_t - last_t) / steps
                                    else:
                                        aligned_timestamps[i] = last_t + 3.0
                                        
                                if aligned_timestamps[i] < last_t:
                                    aligned_timestamps[i] = last_t + 0.1
                                last_t = aligned_timestamps[i]
                                
                        for i, ref in enumerate(ref_lines):
                            t = aligned_timestamps[i]
                            if i == 0 and lyrics_start_val > 0:
                                t = lyrics_start_val
                                
                            m = int(t // 60)
                            s = int(t % 60)
                            ms = int((t % 1) * 100)
                            timestamp = f"[{m:02d}:{s:02d}.{ms:02d}]"
                            lrc_lines.append(f"{timestamp}{ref}")
                
                clean_lines = [line.strip() for line in lrc_lines if line.strip()]
                draft_lrc = "\n".join(clean_lines)
                
                # Salva o arquivo lyrics.lrc gerado e alinhado automaticamente
                lrc_path = song_dir / "lyrics.lrc"
                with open(lrc_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(draft_lrc)
                    
                # Roda o prepare_song imediatamente para alinhar no nível das palavras!
                sys.path.append(str(Path(__file__).parent.parent / "tools"))
                from prepare_song import prepare_song
                prepare_song(str(song_dir), language)
                
                return {"success": True, "lyrics_status": "ready", "slug": slug, "fallback_used": fallback_used}
                
            else:
                # Caso tradicional: transcreve com o Whisper e gera rascunho de LRC para edição manual
                lrc_lines = [
                    f"[ti:{title}]",
                    f"[ar:{artist}]",
                    ""
                ]
                for i, seg in enumerate(segments_list):
                    # O bug de silêncio inicial do Whisper zera apenas o tempo do primeiro vocal
                    if i == 0 and lyrics_start_val > 0:
                        shifted_start = lyrics_start_val
                    else:
                        shifted_start = seg.start
                    
                    m = int(shifted_start // 60)
                    s = int(shifted_start % 60)
                    ms = int((shifted_start % 1) * 100)
                    timestamp = f"[{m:02d}:{s:02d}.{ms:02d}]"
                    lrc_lines.append(f"{timestamp}{seg.text.strip()}")
                    
                draft_lrc = "\n".join(lrc_lines)
                
                return {
                    "success": True, 
                    "lyrics_status": "draft", 
                    "draft_lrc": draft_lrc, 
                    "slug": slug,
                    "fallback_used": False
                }
            
    except Exception as e:
        logger.error(f"Erro ao adicionar música: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/get-ip")
async def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return {"ip": ip}

@app.get("/api/get-lyrics")
async def get_lyrics(slug: str, response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    try:
        songs_dir = Path(__file__).parent / "songs"
        song_dir = songs_dir / slug
        lrc_path = song_dir / "lyrics.lrc"
        if not lrc_path.exists():
            return {"success": False, "lyrics": "", "language": "en"}
            
        with open(lrc_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        clean_lines = [line.strip() for line in content.splitlines() if line.strip()]
        content = "\n".join(clean_lines)
            
        # Detecta automaticamente o idioma a partir dos segmentos salvos
        language = "en"
        segments_path = song_dir / "segments.json"
        if segments_path.exists():
            try:
                with open(segments_path, "r", encoding="utf-8") as sf:
                    segs = json.load(sf)
                    if segs and len(segs) > 0:
                        language = segs[0].get("language", "en")
            except Exception as e:
                logger.debug(f"Falha ao ler language de segments.json: {e}")

        return {"success": True, "lyrics": content, "language": language}
    except Exception as e:
        logger.error(f"Erro ao obter letras: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save-lyrics")
async def save_lyrics(
    slug: str = Form(...),
    language: str = Form("en"),
    lyrics_lrc: str = Form(...)
):
    try:
        songs_dir = Path(__file__).parent / "songs"
        song_dir = songs_dir / slug
        if not song_dir.exists():
            raise HTTPException(status_code=404, detail="Diretório da música não encontrado")
            
        # Salva o arquivo de letras LRC enviado sem linhas em branco
        clean_lines = [line.strip() for line in lyrics_lrc.splitlines() if line.strip()]
        clean_lyrics = "\n".join(clean_lines)
        lrc_path = song_dir / "lyrics.lrc"
        with open(lrc_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(clean_lyrics)
            
        # Roda o pipeline de alinhamento prepare_song
        sys.path.append(str(Path(__file__).parent.parent / "tools"))
        from prepare_song import prepare_song
        prepare_song(str(song_dir), language)
        
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Erro ao salvar letras e processar alinhamento: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/delete-song/{song_id}")
async def delete_song(song_id: str):
    try:
        songs_dir = Path(__file__).parent / "songs"
        song_dir = songs_dir / song_id
        if not song_dir.exists():
            raise HTTPException(status_code=404, detail="Música não encontrada")
        
        # Remove a pasta da música inteira
        shutil.rmtree(song_dir)
        logger.info(f"Música deletada do disco: {song_id}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Erro ao deletar a música {song_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Em produção, carregar caminhos de cert.pem e key.pem
    uvicorn.run(app, host="0.0.0.0", port=8000)
