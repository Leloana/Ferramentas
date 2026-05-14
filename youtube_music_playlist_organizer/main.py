import argparse
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import OLLAMA_MODEL_DEFAULT, API_DAILY_LIMIT
from ytmusic_client import YTMusicClient
from youtube_client import YouTubeClient
from classifier import GenreClassifier
from organizer import Organizer

console = Console()

def print_report(total_tracks, genres_found, created, updated, quota_used, genre_stats):
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("Músicas processadas", f": {total_tracks}")
    table.add_row("Gêneros encontrados", f": {genres_found}")
    table.add_row("Playlists criadas", f": {created}")
    table.add_row("Playlists atualizadas", f": {updated}")
    table.add_row("Unidades API usadas", f": {quota_used} / {API_DAILY_LIMIT}")

    genre_table = Table(show_header=False, box=None)
    genre_table.add_column("Genre")
    genre_table.add_column("Count")
    
    # Sort genres by count descending
    sorted_genres = sorted(genre_stats.items(), key=lambda x: x[1], reverse=True)
    for genre, count in sorted_genres:
        genre_table.add_row(genre.ljust(12), f"→ {count} músicas")

    content = f"{table}\n\n{genre_table}"
    
    console.print(Panel.fit(
        content,
        title="[bold]YouTube Playlist Organizer — Done[/bold]",
        border_style="green",
        padding=(1, 2)
    ))

def main():
    parser = argparse.ArgumentParser(description="YouTube Music Playlist Organizer")
    parser.add_argument("--source-playlist", required=True, help="ID da playlist fonte")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que faria sem modificar nada")
    parser.add_argument("--model", default=OLLAMA_MODEL_DEFAULT, help=f"Modelo Ollama a usar (padrão: {OLLAMA_MODEL_DEFAULT})")
    
    args = parser.parse_args()

    console.print(f"[cyan]Iniciando leitura da playlist {args.source_playlist}...[/cyan]")
    
    try:
        yt_music_client = YTMusicClient()
    except Exception as e:
        console.print(f"[red]Erro ao inicializar YTMusic:[/red] {e}")
        sys.exit(1)

    tracks = yt_music_client.get_playlist_items(args.source_playlist)
    console.print(f"[green]Encontradas {len(tracks)} músicas na playlist fonte.[/green]")

    if not tracks:
        console.print("[yellow]Nenhuma música encontrada.[/yellow]")
        sys.exit(0)

    console.print(f"[cyan]Iniciando classificação com modelo Ollama ({args.model})...[/cyan]")
    classifier = GenreClassifier(args.model)
    
    classified_tracks = []
    with console.status("[bold green]Classificando músicas...") as status:
        for idx, track in enumerate(tracks):
            genre = classifier.classify(track['title'], track['artist'])
            track['genre'] = genre
            classified_tracks.append(track)
            status.update(f"[bold green]Classificando músicas... ({idx+1}/{len(tracks)})")

    organizer = Organizer()
    grouped_tracks = organizer.group_by_genre(classified_tracks)
    
    genre_stats = {genre: len(items) for genre, items in grouped_tracks.items()}
    genres_found = len(grouped_tracks)
    total_tracks = len(classified_tracks)
    
    created_count = 0
    updated_count = 0
    quota_used = 0

    if args.dry_run:
        console.print("[yellow]Execução DRY-RUN, nenhuma alteração será feita no YouTube.[/yellow]")
    else:
        console.print("[cyan]Sincronizando com o YouTube (Data API v3)...[/cyan]")
        try:
            yt_client = YouTubeClient()
            
            existing_playlists = yt_client.get_user_playlists()
            
            for genre, items in grouped_tracks.items():
                playlist_title = f"{genre.capitalize()} (Auto)"
                
                if playlist_title in existing_playlists:
                    playlist_id = existing_playlists[playlist_title]
                    console.print(f"Playlist '[blue]{playlist_title}[/blue]' já existe. Atualizando...")
                    updated_count += 1
                else:
                    console.print(f"Criando playlist '[blue]{playlist_title}[/blue]'...")
                    playlist_id = yt_client.create_playlist(playlist_title)
                    created_count += 1
                
                existing_video_ids = yt_client.get_playlist_items(playlist_id)
                
                added = 0
                for item in items:
                    if item['videoId'] not in existing_video_ids:
                        yt_client.add_to_playlist(playlist_id, item['videoId'])
                        existing_video_ids.add(item['videoId']) # Evitar duplicação em sequência
                        added += 1
                
                if added > 0:
                    console.print(f"  + Adicionadas {added} novas músicas.")
                else:
                    console.print(f"  Nenhuma nova música para adicionar.")
            
            quota_used = yt_client.quota_used

        except Exception as e:
            console.print(f"[red]Erro ao sincronizar com o YouTube:[/red] {e}")

    print_report(total_tracks, genres_found, created_count, updated_count, quota_used, genre_stats)

if __name__ == "__main__":
    main()
