from auth import get_ytmusic_client

class YTMusicClient:
    def __init__(self):
        self.ytm = get_ytmusic_client()

    def get_playlist_items(self, playlist_id):
        if playlist_id == "LM":
            results = self.ytm.get_liked_songs(limit=None)
            tracks = results.get('tracks', [])
        else:
            results = self.ytm.get_playlist(playlist_id, limit=None)
            tracks = results.get('tracks', [])
            
        items = []
        for track in tracks:
            title = track.get('title', 'Unknown Title')
            artists = track.get('artists', [])
            artist_name = ", ".join([a['name'] for a in artists]) if artists else 'Unknown Artist'
            album_info = track.get('album')
            album_name = album_info.get('name', 'Unknown Album') if album_info else 'Unknown Album'
            video_id = track.get('videoId')
            
            if video_id:
                items.append({
                    'title': title,
                    'artist': artist_name,
                    'album': album_name,
                    'videoId': video_id
                })
        return items
