import time
import socket
from functools import wraps
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from core.auth import get_youtube_credentials
from core.config import (
    COST_LIST_PLAYLIST_ITEMS, COST_CREATE_PLAYLIST,
    COST_INSERT_PLAYLIST_ITEM, COST_DELETE_PLAYLIST,
)
from core.logger import get_logger
from core.quota_manager import QuotaManager

def retry_with_backoff(max_attempts=4, base_delay=2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except (socket.error, ConnectionError, TimeoutError) as e:
                    attempts += 1
                    if attempts == max_attempts:
                        raise
                    time.sleep(base_delay * (2 ** (attempts - 1)))
                except HttpError as e:
                    status_code = e.resp.status
                    if 500 <= status_code < 600 or status_code == 429:
                        attempts += 1
                        if attempts == max_attempts:
                            raise
                        time.sleep(base_delay * (2 ** (attempts - 1)))
                    else:
                        raise
        return wrapper
    return decorator

class YouTubeClient:
    def __init__(self):
        self.logger = get_logger()
        self.logger.info("Conectando ao YouTube Data API v3...")
        try:
            socket.setdefaulttimeout(30)
            self.creds = get_youtube_credentials()
            self.youtube = build('youtube', 'v3', credentials=self.creds)
            self.logger.info("Conexão com YouTube estabelecida com sucesso.")
        except Exception as e:
            self.logger.error(f"Falha ao conectar ao YouTube: {e}")
            raise

    def get_user_playlists(self):
        self.logger.debug("Listando playlists do usuário...")
        playlists = {}
        request = self.youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50
        )
        while request is not None:
            QuotaManager.add_usage(COST_LIST_PLAYLIST_ITEMS)
            response = request.execute()
            for item in response.get("items", []):
                title = item["snippet"]["title"]
                playlists[title] = item["id"]
            request = self.youtube.playlists().list_next(request, response)
        return playlists

    @retry_with_backoff(max_attempts=4, base_delay=2.0)
    def create_playlist(self, name, description=""):
        self.logger.info(f"Criando nova playlist: {name}")
        try:
            request = self.youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": name,
                        "description": description,
                        "defaultLanguage": "pt"
                    },
                    "status": {
                        "privacyStatus": "private"
                    }
                }
            )
            QuotaManager.add_usage(COST_CREATE_PLAYLIST)
            response = request.execute()
            self.logger.info(f"Playlist criada com sucesso! ID: {response['id']}")
            return response['id']
        except Exception as e:
            self.logger.error(f"❌ Erro ao criar playlist '{name}': {e}")
            return None

    def get_playlist_items(self, playlist_id):
        self.logger.debug(f"Buscando itens da playlist: {playlist_id}")
        video_ids = set()
        try:
            request = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50
            )
            while request is not None:
                QuotaManager.add_usage(COST_LIST_PLAYLIST_ITEMS)
                response = request.execute()
                for item in response.get("items", []):
                    video_id = item["snippet"]["resourceId"]["videoId"]
                    video_ids.add(video_id)
                request = self.youtube.playlistItems().list_next(request, response)
        except Exception as e:
            self.logger.warning(f"⚠️ Não foi possível listar itens da playlist {playlist_id}: {e}")
        return video_ids

    @retry_with_backoff(max_attempts=4, base_delay=2.0)
    def add_to_playlist(self, playlist_id, video_id):
        self.logger.debug(f"Adicionando vídeo {video_id} à playlist {playlist_id}")
        try:
            request = self.youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id
                        }
                    }
                }
            )
            QuotaManager.add_usage(COST_INSERT_PLAYLIST_ITEM)
            response = request.execute()
            return response
        except Exception as e:
            self.logger.error(f"❌ Erro ao adicionar vídeo {video_id} na playlist {playlist_id}: {e}")
            return None

    @retry_with_backoff(max_attempts=4, base_delay=2.0)
    def delete_playlist(self, playlist_id):
        self.logger.info(f"Removendo playlist: {playlist_id}")
        # Conta a cota antes do envio: a chamada gasta unidades mesmo que falhe
        # por erro de servidor, e é melhor superestimar do que estourar o limite.
        QuotaManager.add_usage(COST_DELETE_PLAYLIST)
        self.youtube.playlists().delete(id=playlist_id).execute()
        return True
