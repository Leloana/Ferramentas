import json
import logging
import asyncio
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import Optional
import re
import shutil
import sys
import os

# Garante que a pasta server está no path do Python para localizador de módulos
server_dir = str(Path(__file__).parent.absolute())
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

# Localizador Dinâmico Inteligente de FFmpeg no Windows
winget_packages_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"))
ffmpeg_bin_dir = None

# 1. Busca recursivamente no diretório de pacotes instalados pelo Winget
if winget_packages_dir.exists():
    for p in winget_packages_dir.glob("**/bin/ffmpeg.exe"):
        ffmpeg_bin_dir = str(p.parent)
        break

# 2. Fallback para o diretório de atalhos Links do Winget
if not ffmpeg_bin_dir:
    winget_links_path = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links")
    if Path(winget_links_path).exists():
        ffmpeg_bin_dir = winget_links_path

# Injeta a pasta localizada no PATH do ambiente ativo
if ffmpeg_bin_dir:
    if ffmpeg_bin_dir not in os.environ["PATH"]:
        os.environ["PATH"] += os.pathsep + ffmpeg_bin_dir

from pydub import AudioSegment

# Configura explicitamente os conversores no pydub
if ffmpeg_bin_dir:
    ffmpeg_exe = Path(ffmpeg_bin_dir) / "ffmpeg.exe"
    if ffmpeg_exe.exists():
        AudioSegment.converter = str(ffmpeg_exe)
        ffprobe_exe = Path(ffmpeg_bin_dir) / "ffprobe.exe"
        if ffprobe_exe.exists():
            AudioSegment.ffprobe = str(ffprobe_exe)

from stt_engine import get_stt_engine
from score_engine import calculate_score
from song_manager import SongManager

# Configurações
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Gerenciamento de Salas Multi-Dispositivo
class KaraokeRoom:
    def __init__(self, song_id: str):
        self.song_id = song_id
        self.display: Optional[WebSocket] = None
        self.mic: Optional[WebSocket] = None
        self.audio_buffer = bytearray()
        self.client_sample_rate = 48000
        self.current_segment_idx = 0
        self.transcribed_segments = set()
        self.total_score = 0.0
        self.last_client_time = 0.0
        self.segments = []
        self.is_active = True
        self.is_singing_active = False

class RoomManager:
    def __init__(self):
        self.rooms = {} # room_id -> KaraokeRoom

    def get_or_create_room(self, room_id: str, song_id: str, segments: list) -> KaraokeRoom:
        if room_id not in self.rooms:
            room = KaraokeRoom(song_id)
            room.segments = segments
            self.rooms[room_id] = room
            logger.info(f"Sala de Karaokê criada: {room_id} para a música {song_id}")
        return self.rooms[room_id]

    def clean_room(self, room_id: str):
        if room_id in self.rooms:
            room = self.rooms[room_id]
            if not room.display and not room.mic:
                del self.rooms[room_id]
                logger.info(f"Sala de Karaokê removida por inatividade: {room_id}")

room_manager = RoomManager()
song_manager = SongManager()
app = FastAPI(title="Karaoke MVP Server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas HTTP
@app.get("/")
async def get_index(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return FileResponse(Path(__file__).parent.parent / "client" / "index.html")

@app.get("/songs")
@app.get("/api/songs")
async def list_songs(response: Response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return song_manager.list_songs()

@app.get("/songs/{song_id}/audio")
async def get_audio(song_id: str):
    audio_path = song_manager.get_audio_path(song_id)
    if not audio_path:
        raise HTTPException(status_code=404, detail="Música não encontrada")
    return FileResponse(audio_path)

# WebSocket
@app.websocket("/ws/{song_id}")
async def websocket_endpoint(websocket: WebSocket, song_id: str):
    await websocket.accept()
    
    song_data = song_manager.get_song_data(song_id)
    if not song_data:
        await websocket.close(code=1008, reason="Música não encontrada")
        return

# WebSocket
@app.websocket("/ws/room/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    
    # Obtém role e song_id a partir dos parâmetros de query
    role = websocket.query_params.get("role", "display")
    song_id = websocket.query_params.get("song_id")
    
    # Se for display, o song_id é opcional para permitir pareamento inicial na home screen
        
    segments = []
    song_title = ""
    if song_id:
        song_data = song_manager.get_song_data(song_id)
        if not song_data:
            await websocket.close(code=1008, reason="Música não encontrada")
            return
        segments = song_data["segments"]
        song_title = f"{song_data.get('title', '')} - {song_data.get('artist', '')}" if song_data.get('artist') else song_data.get('title', '')

    room = room_manager.get_or_create_room(room_id, song_id or "", segments)
    if song_title:
        room.song_title = song_title
    
    # Se a sala já existe e um novo display conectou para outra música, reinicia a sala para a nova faixa
    if role == "display" and song_id:
        room.song_id = song_id
        room.song_title = song_title
        room.segments = segments
        room.current_segment_idx = 0
        room.transcribed_segments = set()
        room.total_score = 0.0
        room.last_client_time = 0.0
        room.audio_buffer = bytearray()
        room.is_singing_active = False
    
    # Registra o WebSocket no papel correspondente
    if role == "mic":
        if room.mic:
            try:
                await room.mic.close(code=1000, reason="Novo microfone conectado")
            except:
                pass
        room.mic = websocket
        logger.info(f"Microfone conectado para a sala: {room_id}")
        
        # Avisa que pareou com sucesso
        await websocket.send_json({"type": "pairing_status", "status": "paired", "role": "mic"})
        if room.display:
            await room.display.send_json({"type": "pairing_status", "status": "paired", "role": "display"})
            
    else: # role == "display"
        if room.display:
            try:
                await room.display.close(code=1000, reason="Novo display conectado")
            except:
                pass
        room.display = websocket
        logger.info(f"Display (TV) conectado para a sala: {room_id}")
        
        if room.mic:
            await websocket.send_json({"type": "pairing_status", "status": "paired", "role": "display"})
            try:
                await room.mic.send_json({"type": "pairing_status", "status": "paired", "role": "mic"})
            except:
                pass
        else:
            await websocket.send_json({"type": "pairing_status", "status": "unpaired", "role": "display"})
            
    # Envia o estado de canto inicial
    try:
        await websocket.send_json({"type": "singing_state", "active": room.is_singing_active})
    except:
        pass
            
    stt = get_stt_engine()
    
    # Processador em background compartilhado
    async def process_and_score(seg_idx, audio_data, seg_lang, seg_lyrics, seg_text):
        try:
            # Calcule o RMS e duração do áudio original recebido
            duration = len(audio_data) / room.client_sample_rate
            rms_original = np.sqrt(np.mean(audio_data ** 2)) if len(audio_data) > 0 else 0
            
            logger.info(f"\n========================================\n"
                        f"🎤 [DEBUG MICROFONE] Segmento {seg_idx + 1} - Sala {room_id}\n"
                        f"   - Letra Esperada: '{seg_text}'\n"
                        f"   - Duração do Áudio Recebido: {duration:.2f}s ({len(audio_data)} samples)\n"
                        f"   - RMS de Entrada: {rms_original:.6f}\n"
                        f"========================================")

            # Detecção de vocalizes não-lexicais (Oh-oh, La-la-la, etc.)
            vocalize_words = {"oh", "la", "uh", "na", "ah", "oo", "woo", "yeah", "yeh", "wow", "hm", "hmm", "hey", "hei"}
            clean_words = [re.sub(r'[^\w]', '', w.lower()) for w in seg_text.split()]
            is_vocalize = len(clean_words) > 0 and all(w in vocalize_words for w in clean_words if w)

            if is_vocalize:
                # Pontua baseado apenas no RMS (se cantou ou não)
                logger.info(f"⚡ [Bypass Vocalize] Detectado trecho não-lexical ('{seg_text}'). Avaliando por energia (RMS: {rms_original:.6f})")
                if rms_original > 0.008:
                    score = 100.0
                    transcribed_text = seg_text
                    transcription_processed = seg_text
                    matched_count = len(clean_words)
                elif rms_original > 0.002:
                    score = 50.0
                    transcribed_text = "(som baixo)"
                    transcription_processed = "(som baixo)"
                    matched_count = len(clean_words) // 2
                else:
                    score = 0.0
                    transcribed_text = "(silêncio)"
                    transcription_processed = "(silêncio)"
                    matched_count = 0

                room.total_score += score
                result = {
                    "score": score,
                    "transcription": transcription_processed,
                    "matched_words": matched_count,
                    "total_expected": len(clean_words)
                }
            else:
                # 2. Resample e Transcrever (com initial_prompt para guiar a IA)
                def compute():
                    # Resampling ultra-rápido via interpolação linear (Numpy) ao invés do lento Fourier Resample do SciPy
                    duration = len(audio_data) / room.client_sample_rate
                    num_target_samples = int(duration * 16000)
                    x_orig = np.linspace(0, duration, len(audio_data))
                    x_target = np.linspace(0, duration, num_target_samples)
                    resampled = np.interp(x_target, x_orig, audio_data).astype(np.float32)
                    return stt.transcribe(resampled, language=seg_lang, initial_prompt=seg_text)
                    
                transcribed_text, words = await asyncio.to_thread(compute)
                
                prev_lyrics = None
                if seg_idx > 0 and seg_idx - 1 < len(room.segments):
                    prev_lyrics = room.segments[seg_idx - 1]["lyrics"].split()
                
                # 4. Pontuar
                result = calculate_score(seg_lyrics, words, prev_expected_words=prev_lyrics)
                room.total_score += result["score"]
            
            logger.info(f"\n========================================\n"
                        f"📝 [DEBUG TRANSCRIÇÃO] Segmento {seg_idx + 1} - Sala {room_id}\n"
                        f"   - Texto Transcrito (Whisper): '{transcribed_text}'\n"
                        f"   - Palavras Mapeadas: {result['matched_words']}/{result['total_expected']}\n"
                        f"   - Transcrição acústica processada: '{result['transcription']}'\n"
                        f"   - Pontuação Deste Segmento: {result['score']}%\n"
                        f"   - Média de Pontuação Geral Atual: {round(room.total_score / (seg_idx + 1), 1)}%\n"
                        f"========================================")
            
            # Envia resultados para os dois dispositivos se estiverem conectados
            response_msg = {
                "type": "segment_result",
                "score": result["score"],
                "transcription": result["transcription"],
                "total_score": round(room.total_score / (seg_idx + 1), 1)
            }
            if room.display:
                await room.display.send_json(response_msg)
            if room.mic:
                await room.mic.send_json(response_msg)
        except Exception as e:
            logger.error(f"Erro no processamento do segmento: {e}", exc_info=True)

    try:
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                # Recebendo chunks de áudio PCM Float32 do microfone ativo
                if room.current_segment_idx < len(room.segments):
                    current_seg = room.segments[room.current_segment_idx]
                    current_time = room.last_client_time
                    
                    # Só acumula áudio se estiver dentro da janela de canto ativa (com margem de 1.5s antes e 0.5s depois para estiramento vocal)
                    # Isso evita acúmulo de áudio durante introdução ou longas pausas instrumentais, eliminando o delay de alinhamento.
                    if current_time >= (current_seg["sing_start"] - 1.5) and current_time <= (current_seg["sing_end"] + 0.5):
                        room.audio_buffer.extend(message["bytes"])
                
            elif "text" in message:
                data = json.loads(message["text"])
                msg_type = data.get("type")
                
                if msg_type == "client_info":
                    room.client_sample_rate = data.get("sample_rate", 48000)
                    logger.info(f"Sample rate do cliente na sala {room_id}: {room.client_sample_rate}")
                    
                    # Envia o início do primeiro segmento
                    if room.display:
                        await send_segment_start(room.display, room.segments, 0, room.song_title)
                    if room.mic:
                        await send_segment_start(room.mic, room.segments, 0, room.song_title)
                    
                elif msg_type == "playback_time":
                    # Apenas o display atualiza o tempo principal do player de áudio
                    current_time = data.get("current_time", 0.0)
                    room.last_client_time = current_time
                    
                    # Determina se há canto ativo no momento (com margem de 1.0s antes e 0.5s depois)
                    is_singing = False
                    if room.current_segment_idx < len(room.segments):
                        current_seg = room.segments[room.current_segment_idx]
                        is_singing = current_time >= (current_seg["sing_start"] - 1.0) and current_time <= (current_seg["sing_end"] + 0.5)
                    
                    if is_singing != room.is_singing_active:
                        room.is_singing_active = is_singing
                        state_msg = {"type": "singing_state", "active": is_singing}
                        if room.display:
                            try:
                                await room.display.send_json(state_msg)
                            except:
                                pass
                        if room.mic:
                            try:
                                await room.mic.send_json(state_msg)
                            except:
                                pass
                    
                    # Lógica de transição de segmentos compartilhada
                    if room.current_segment_idx < len(room.segments):
                        current_seg = room.segments[room.current_segment_idx]
                        
                        # Se vamos transicionar ou se já passou do fim da janela de canto (com 0.5s de atraso extra), processa a transcrição
                        should_transcribe = current_time >= (current_seg["sing_end"] + 0.5) or current_time >= current_seg["pause_end"] - 0.15
                        
                        if should_transcribe and room.audio_buffer and room.current_segment_idx not in room.transcribed_segments:
                            room.transcribed_segments.add(room.current_segment_idx)
                            logger.info(f"Processando segmento {room.current_segment_idx + 1} para a sala {room_id}")
                            
                            # 1. Converter buffer para numpy float32
                            raw_audio = np.frombuffer(room.audio_buffer, dtype=np.float32).copy()
                            room.audio_buffer = bytearray() # Limpa para o próximo
                            
                            # Lança tarefa de transcrição em background
                            asyncio.create_task(process_and_score(
                                room.current_segment_idx, 
                                raw_audio, 
                                current_seg["language"], 
                                current_seg["lyrics_timed"],
                                current_seg["lyrics"]
                            ))
                            
                        # Transiciona para o próximo segmento imediatamente ao término do canto (sing_end)
                        # Isso dá tempo ao front-end de receber a letra do próximo verso e exibir a barra de silêncio
                        if current_time >= current_seg["sing_end"]:
                            room.current_segment_idx += 1
                            if room.current_segment_idx < len(room.segments):
                                if room.display:
                                    await send_segment_start(room.display, room.segments, room.current_segment_idx, room.song_title)
                                if room.mic:
                                    await send_segment_start(room.mic, room.segments, room.current_segment_idx, room.song_title)
                            else:
                                logger.info(f"Último segmento cantado na sala {room_id}. Aguardando o backing track terminar...")
                                outro_msg = {"type": "outro_start"}
                                if room.display:
                                    try:
                                        await room.display.send_json(outro_msg)
                                    except:
                                        pass
                                if room.mic:
                                    try:
                                        await room.mic.send_json(outro_msg)
                                    except:
                                        pass
                                
                elif msg_type == "audio_ended":
                    logger.info(f"Áudio finalizado pelo cliente na sala {room_id}. Finalizando jogo...")
                    total_score_avg = round(room.total_score / max(1, len(room.segments)), 1)
                    game_over_msg = {
                        "type": "game_over",
                        "total_score": total_score_avg
                    }
                    if room.display:
                        await room.display.send_json(game_over_msg)
                    if room.mic:
                        await room.mic.send_json(game_over_msg)
                    break
                                
    except (WebSocketDisconnect, RuntimeError):
        logger.info(f"Conexão do papel {role} desconectada na sala {room_id}.")
    except Exception as e:
        logger.error(f"Erro no WebSocket da sala {room_id}: {e}", exc_info=True)
    finally:
        # Limpa o websocket do respectivo papel ao desconectar
        if role == "mic":
            room.mic = None
            if room.display:
                try:
                    await room.display.send_json({"type": "pairing_status", "status": "unpaired", "role": "mic"})
                except:
                    pass
        else:
            room.display = None
            if room.mic:
                try:
                    await room.mic.send_json({"type": "pairing_status", "status": "unpaired", "role": "display"})
                except:
                    pass
                    
        # Fecha a conexão fisicamente
        try:
            await websocket.close()
        except:
            pass
            
        # Deleta a sala inteira se todos os participantes desconectarem
        room_manager.clean_room(room_id)

async def send_segment_start(ws: WebSocket, segments: list, idx: int, song_title: str = ""):
    segment = segments[idx]
    prev_lyrics = segments[idx - 1]["lyrics"] if idx > 0 else ""
    next_lyrics = segments[idx + 1]["lyrics"] if idx < len(segments) - 1 else ""
    
    await ws.send_json({
        "type": "segment_start",
        "id": segment["id"],
        "label": segment["label"],
        "sing_start": segment["sing_start"],
        "sing_end": segment["sing_end"],
        "lyrics": segment["lyrics"],
        "lyrics_timed": segment["lyrics_timed"],
        "prev_lyrics": prev_lyrics,
        "next_lyrics": next_lyrics,
        "song_title": song_title
    })

def slugify(text: str) -> str:
    # Converte para minúsculas, remove acentos simplificados e substitui espaços por traços
    text = text.lower().strip()
    # Substituições comuns de caracteres com acento em português
    replacements = {
        'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'ç': 'c', 'ñ': 'n'
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text

def parse_time_to_seconds(time_str: str) -> float:
    # Converte string de tempo flexível (ex: "4:30", "04:30.5", "10") para segundos (float)
    time_str = str(time_str).strip()
    if not time_str or time_str == "-1.0" or time_str == "-1":
        return -1.0
        
    try:
        return float(time_str)
    except ValueError:
        pass
        
    parts = time_str.split(':')
    try:
        if len(parts) == 2:
            m = float(parts[0])
            s = float(parts[1])
            return m * 60 + s
        elif len(parts) == 3:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s
    except Exception as e:
        logger.error(f"Erro ao converter string de tempo '{time_str}': {e}")
        
    return 0.0

async def download_youtube_audio(url: str, output_path: Path) -> bool:
    """Downloads audio from a YouTube URL and converts it to MP3 using yt-dlp and FFmpeg."""
    import yt_dlp
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_template = str(output_path.with_suffix("")) + ".%(ext)s"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': temp_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    
    if ffmpeg_bin_dir:
        ydl_opts['ffmpeg_location'] = ffmpeg_bin_dir
        
    try:
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
        await asyncio.to_thread(download)
    except Exception as e:
        logger.warning(f"Aviso nao-critico durante download do YouTube: {e}")
        
    expected_file = output_path.with_suffix(".mp3")
    if expected_file.exists() and expected_file.stat().st_size > 1000:
        if expected_file != output_path:
            try:
                shutil.move(str(expected_file), str(output_path))
            except Exception as move_err:
                logger.warning(f"Aviso ao mover arquivo mp3: {move_err}")
                
        # Limpeza proativa de arquivos residuais (.webm, .m4a, .part) causados por concorrencia no Windows
        for ext in [".webm", ".m4a", ".part"]:
            leftover = output_path.with_suffix(ext)
            if leftover.exists():
                try:
                    leftover.unlink()
                except Exception as unlink_err:
                    logger.debug(f"Nao foi possivel remover arquivo residual {leftover}: {unlink_err}")
                    
        return True
        
    return False

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
            v_task = download_youtube_audio(youtube_vocal_url.strip(), temp_vocal_path)
            b_task = download_youtube_audio(youtube_backing_url.strip(), temp_backing_path)
            
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
    import socket
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
            except:
                pass
                
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
