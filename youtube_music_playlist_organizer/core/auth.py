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
        raise FileNotFoundError(
            "O arquivo [bold]oauth.json[/bold] não foi encontrado.\n\n"
            "Por favor, rode o script de configuração para gerá-lo:\n"
            "[bold cyan].\\venv\\Scripts\\python setup_oauth.py[/bold cyan]"
        )
    
    try:
        # 1. Lê o arquivo original
        with open("oauth.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 2. Extrai credenciais para o refresh
        from ytmusicapi.auth.oauth.credentials import OAuthCredentials
        client_id = data.get('client_id')
        client_secret = data.get('client_secret')
        
        if not client_id or not client_secret:
             raise Exception("client_id ou client_secret não encontrados no oauth.json")
             
        creds = OAuthCredentials(client_id, client_secret)

        # 3. Cria um dicionário limpo apenas com o que a biblioteca aceita
        # Isso evita o erro de 'unexpected keyword argument'
        valid_keys = ['access_token', 'refresh_token', 'expires_at', 'expires_in', 'token_type', 'scope']
        clean_data = {k: v for k, v in data.items() if k in valid_keys}
        
        # 4. Salva um arquivo temporário limpo para a biblioteca ler
        with open("oauth_managed.json", "w", encoding="utf-8") as f:
            json.dump(clean_data, f)

        # 5. Inicializa com o arquivo limpo e as credenciais explícitas
        return YTMusic(auth="oauth_managed.json", oauth_credentials=creds)

    except Exception as e:
        raise Exception(f"Falha na autenticação do YT Music: {str(e)}")
