import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv
from ytmusicapi import YTMusic

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly', 'https://www.googleapis.com/auth/youtube.force-ssl']
TOKEN_FILE = 'token.json'

def get_youtube_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_id = os.getenv("YOUTUBE_CLIENT_ID")
            client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
            
            if not client_id or not client_secret:
                raise ValueError("YOUTUBE_CLIENT_ID e YOUTUBE_CLIENT_SECRET devem estar no .env")
                
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "project_id": "youtube-organizer",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                    "client_secret": client_secret,
                    "redirect_uris": ["http://localhost"]
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = flow.run_local_server(port=0)
            
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return creds

def get_ytmusic_client():
    if not os.path.exists("oauth.json"):
        raise FileNotFoundError("Arquivo oauth.json não encontrado. Execute 'ytmusicapi oauth' no terminal primeiro.")
    return YTMusic("oauth.json")
