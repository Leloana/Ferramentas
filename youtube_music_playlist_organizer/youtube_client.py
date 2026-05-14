from googleapiclient.discovery import build
from auth import get_youtube_credentials
from config import COST_LIST_PLAYLIST_ITEMS, COST_CREATE_PLAYLIST, COST_INSERT_PLAYLIST_ITEM

class YouTubeClient:
    def __init__(self):
        self.creds = get_youtube_credentials()
        self.youtube = build('youtube', 'v3', credentials=self.creds)
        self.quota_used = 0

    def get_user_playlists(self):
        playlists = {}
        request = self.youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50
        )
        while request is not None:
            response = request.execute()
            self.quota_used += COST_LIST_PLAYLIST_ITEMS
            for item in response.get("items", []):
                title = item["snippet"]["title"]
                playlists[title] = item["id"]
            request = self.youtube.playlists().list_next(request, response)
        return playlists

    def create_playlist(self, title):
        request = self.youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": title,
                    "description": "Playlist gerada automaticamente pelo YouTube Music Organizer"
                },
                "status": {
                    "privacyStatus": "private"
                }
            }
        )
        response = request.execute()
        self.quota_used += COST_CREATE_PLAYLIST
        return response["id"]

    def get_playlist_items(self, playlist_id):
        video_ids = set()
        request = self.youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50
        )
        while request is not None:
            response = request.execute()
            self.quota_used += COST_LIST_PLAYLIST_ITEMS
            for item in response.get("items", []):
                video_id = item["snippet"]["resourceId"]["videoId"]
                video_ids.add(video_id)
            request = self.youtube.playlistItems().list_next(request, response)
        return video_ids

    def add_to_playlist(self, playlist_id, video_id):
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
        response = request.execute()
        self.quota_used += COST_INSERT_PLAYLIST_ITEM
        return response
