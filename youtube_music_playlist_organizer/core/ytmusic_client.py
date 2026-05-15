from core.youtube_client import YouTubeClient
from core.logger import get_logger

class YTMusicClient:
    def __init__(self):
        self.logger = get_logger()
        self.logger.info("Usando Google Data API v3 para leitura...")
        # Usamos o YouTubeClient oficial que já está autorizado com token.json
        self.client = YouTubeClient()

    def get_playlist_items(self, playlist_id):
        target_id = 'LL' if playlist_id == 'LM' else playlist_id
        self.logger.info(f"Buscando músicas da playlist: {target_id}")
        
        raw_items = []
        try:
            request = self.client.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=target_id,
                maxResults=50
            )
            
            while request is not None:
                from core.quota_manager import QuotaManager
                QuotaManager.add_usage(1)
                response = request.execute()
                raw_items.extend(response.get("items", []))
                request = self.client.youtube.playlistItems().list_next(request, response)
                if len(raw_items) >= 500: break
        except Exception as e:
            self.logger.warning(f"⚠️ Não foi possível ler a playlist {target_id}: {e}")
            return []

        self.logger.info(f"Total bruto recuperado: {len(raw_items)}. Iniciando pré-filtro...")

        # Processamento em lotes de 50 para pegar as categorias
        final_tracks = []
        for i in range(0, len(raw_items), 50):
            batch = raw_items[i:i+50]
            video_ids = [item['contentDetails']['videoId'] for item in batch]
            
            # Busca detalhes dos vídeos (incluindo categoria)
            from core.quota_manager import QuotaManager
            QuotaManager.add_usage(1)
            video_details = self.client.youtube.videos().list(
                part="snippet",
                id=",".join(video_ids)
            ).execute()
            
            # Mapeia detalhes por ID
            details_map = {v['id']: v['snippet'] for v in video_details.get('items', [])}
            
            for item in batch:
                vid = item['contentDetails']['videoId']
                snippet = details_map.get(vid, item['snippet'])
                
                category_id = snippet.get('categoryId')
                title = snippet.get('title', '').lower()
                
                # FILTROS DE EXCLUSÃO (Antes da IA)
                # 10 = Music
                is_music_category = (category_id == "10")
                is_blacklisted = any(word in title for word in ['gameplay', 'vlog', 'tutorial', 'aula de', 'react'])
                
                if is_music_category and not is_blacklisted:
                    # Tenta pegar o nome do artista/canal de ambos os campos possíveis na API
                    artist = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or "Unknown Artist"
                    
                    if artist.endswith(" - Topic"): artist = artist[:-8]
                    
                    final_tracks.append({
                        'title': snippet.get('title'),
                        'artist': artist,
                        'id': vid,
                        'liked_at': snippet.get('publishedAt') # Data da curtida
                    })
                else:
                    self.logger.debug(f"Pré-descartado (Cat:{category_id}): {snippet.get('title')}")

        self.logger.info(f"Músicas restantes após pré-filtro: {len(final_tracks)}")
        return final_tracks

    def get_user_playlists(self):
        self.logger.info("Buscando suas playlists existentes...")
        playlists = {}
        request = self.client.youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50
        )
        
        try:
            while request is not None:
                from core.quota_manager import QuotaManager
                QuotaManager.add_usage(1)
                response = request.execute()
                for item in response.get("items", []):
                    title = item["snippet"]["title"]
                    playlists[title] = item["id"]
                request = self.client.youtube.playlists().list_next(request, response)
        except Exception as e:
            self.logger.error(f"Erro ao buscar playlists (API Quota?): {e}")
            
        return playlists
