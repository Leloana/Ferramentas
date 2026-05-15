import argparse
import sys
import random
import time
import logging
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import box
import signal
import atexit

from core.config import OLLAMA_MODEL_DEFAULT, API_DAILY_LIMIT
from core.ytmusic_client import YTMusicClient
from core.youtube_client import YouTubeClient
from core.classifier import MusicClassifier
from core.organizer import Organizer
from core.logger import setup_logger
from core.dataset_manager import DatasetManager
from core.checkpoint_manager import CheckpointManager

console = Console()

class ShutdownHandler:
    def __init__(self, cache_manager, cache_data):
        self.cache_manager = cache_manager
        self.cache_data = cache_data
        self.shutdown_handled = False
        atexit.register(self.handle_shutdown)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        self.handle_shutdown()
        sys.exit(1)

    def handle_shutdown(self):
        if self.shutdown_handled: return
        self.shutdown_handled = True
        logger = logging.getLogger("YTOrganizer")
        logger.warning("Shutdown abrupto detectado (SIGINT/SIGTERM/Exit). Executando cleanup...")
        try:
            self.cache_manager.save_cache(self.cache_data)
        except Exception as e:
            logger.error(f"Falha ao salvar cache no shutdown: {e}")
        for handler in logger.handlers:
            handler.flush()

def check_quota_limit(total_quota_est, args):
    from core.quota_manager import QuotaManager
    daily_used, _ = QuotaManager.get_current_usage()
    quota_remaining = API_DAILY_LIMIT - daily_used
    if total_quota_est > quota_remaining:
        msg = f"Orçamento estimado ({total_quota_est}) excede o saldo restante diário ({quota_remaining})."
        if getattr(args, 'force', False):
            console.print(f"⚠️ [bold yellow]ALERTA:[/bold yellow] {msg} Ignorando bloqueio devido à flag --force.")
        else:
            raise Exception(f"{msg}\nExecute com --force se tiver certeza que possui limite sobrando.")

import questionary
from questionary import Style

custom_theme = Style([
    ('qmark', 'fg:#ff00ff bold'),
    ('question', 'bold fg:#00ffff'),
    ('answer', 'fg:#00ff00 bold'),
    ('pointer', 'fg:#ff00ff bold'),
    ('highlighted', 'fg:#00ffff bold'),
    ('selected', 'fg:#00ff00'),
    ('separator', 'fg:#ff00ff'),
    ('instruction', 'fg:#888888 italic')
])

ASCII_HEADER = r"""[bold magenta]
    ██╗   ██╗████████╗    ███╗   ███╗██╗   ██╗███████╗██╗ ██████╗
    ╚██╗ ██╔╝╚══██╔══╝    ████╗ ████║██║   ██║██╔════╝██║██╔════╝
     ╚████╔╝    ██║       ██╔████╔██║██║   ██║███████╗██║██║
      ╚██╔╝     ██║       ██║╚██╔╝██║██║   ██║╚════██║██║██║
       ██║      ██║       ██║ ╚═╝ ██║╚██████╔╝███████║██║╚██████╗
       ╚═╝      ╚═╝       ╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝ ╚═════╝
[/bold magenta][bold cyan]
                 ▶  P L A Y L I S T   O R G A N I Z E R
[/bold cyan]"""


def print_report(total_tracks, genres_found, created, updated, genre_stats, discarded_count):
    from rich.console import Group
    from core.quota_manager import QuotaManager
    
    daily_used, total_ever = QuotaManager.get_current_usage()
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Músicas processadas", f": {total_tracks}")
    table.add_row("Vídeos descartados", f": {discarded_count}")
    table.add_row("Gêneros finais", f": {genres_found}")
    table.add_row("Playlists criadas", f": {created}")
    table.add_row("Playlists atualizadas", f": {updated}")
    table.add_row("Cota Diária Usada", f": {daily_used} / {API_DAILY_LIMIT}")
    table.add_row("Total Acumulado (Instalação)", f": {total_ever}")

    genre_table = Table(show_header=False, box=None)
    genre_table.add_column("Genre")
    genre_table.add_column("Count")
    
    sorted_genres = sorted(genre_stats.items(), key=lambda x: x[1], reverse=True)
    for genre, count in sorted_genres:
        genre_table.add_row(genre.ljust(15), f"→ {count} músicas")

    content = Group(table, "\n", genre_table)
    console.print(Panel.fit(
        content,
        title="[bold green]YouTube Playlist Organizer — Relatório Final[/bold green]",
        border_style="green",
        padding=(1, 2)
    ))

def show_error(e):
    error_msg = str(e)
    dica = ""
    if "cred" in error_msg.lower() or "token" in error_msg.lower():
        dica = "\n\n💡 [bold yellow]DICA:[/bold yellow] Execute [cyan]python setup_oauth.py[/cyan] para criar ou renovar as chaves de acesso do Google."
    elif "quota" in error_msg.lower():
        dica = "\n\n💡 [bold yellow]DICA:[/bold yellow] A cota diária grátis da API do YouTube esgotou. Volte amanhã ou utilize uma conta/projeto diferente."
    elif "connection" in error_msg.lower() or "connect" in error_msg.lower() or "ollama" in error_msg.lower():
        dica = "\n\n💡 [bold yellow]DICA:[/bold yellow] Certifique-se de que o aplicativo do Ollama está aberto e rodando no computador (tente rodar 'ollama list' no terminal)."
    else:
        dica = "\n\n💡 [bold yellow]DICA:[/bold yellow] Tente rodar o script novamente. Se persistir, verifique sua conexão com a internet."
        
    console.print("\n")
    console.print(Panel(
        f"[bold red]O sistema encontrou um bloqueio:[/bold red]\n\n{error_msg}{dica}",
        title="[bold red]⚠️  ALERTA DO SISTEMA[/bold red]",
        border_style="red",
        padding=(1, 2)
    ))

def evaluate_playlists():
    from core.dataset_manager import DatasetManager
    import questionary
    
    data = DatasetManager.load_dataset()
    unrated = [k for k, v in data.get("playlists", {}).items() if v.get("rating") is None]
    
    if not unrated:
        console.print("\n[yellow]Nenhuma playlist aguardando avaliação no momento.[/yellow]\n")
        return
        
    pl_name = questionary.select(
        "Qual playlist recém-criada você deseja avaliar?",
        choices=unrated + ["Voltar"],
        qmark="🌟", pointer="▶", style=custom_theme
    ).ask()
    
    if not pl_name or pl_name == "Voltar": return
    
    nota = questionary.text(
        f"De 0 a 10, qual nota você dá para a curadoria da playlist '{pl_name}'?",
        validate=lambda text: text.isdigit() and 0 <= int(text) <= 10 or "Digite um número de 0 a 10",
        qmark="🌟", style=custom_theme
    ).ask()
    
    if nota:
        data["playlists"][pl_name]["rating"] = int(nota)
        DatasetManager.save_dataset(data)
        console.print(f"\n[bold green]✅ Nota {nota}/10 salva! A IA aprenderá com esse padrão no futuro.[/bold green]\n")

def main():
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="YouTube Music Playlist Organizer")
    parser.add_argument("--source-playlist", help="ID da playlist fonte")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que faria sem modificar nada")
    parser.add_argument("--model", default=OLLAMA_MODEL_DEFAULT, help=f"Modelo Ollama a usar")
    parser.add_argument("--limit", type=int, help="Limite de músicas")
    parser.add_argument("--since", help="Data DD-MM-AAAA")
    parser.add_argument("--strategy", choices=["genre", "vibe", "time", "season"], help="Estratégia")
    parser.add_argument("--batch-size", type=int, default=15, help="Tamanho do lote para a IA")
    parser.add_argument("--force", action="store_true", help="Ignora bloqueio de cota excedida")
    
    args = parser.parse_args()

    if args.source_playlist:
        run_single_execution(args)
        return

    while True:
        try:
            console.print(ASCII_HEADER)
            mode = questionary.select(
                "Menu Principal:",
                choices=["🎵 Organizar Músicas", "🌟 Avaliar Curadoria (Ensinar IA)", "🚪 Sair"],
                qmark="▶", pointer="▶", style=custom_theme
            ).ask()
            
            if mode == "🚪 Sair" or not mode:
                console.print("[bold cyan]Até logo! 👋[/bold cyan]")
                break
            elif mode == "🌟 Avaliar Curadoria (Ensinar IA)":
                evaluate_playlists()
                input("\nPressione Enter para voltar ao menu...")
                console.clear()
                continue
                
            wizard_args = run_interactive_wizard(args)
            if not wizard_args:
                console.clear()
                continue
                
            run_single_execution(wizard_args)
            console.print("\n" + "─" * 50)
            input("\nPresione Enter para voltar ao menu principal...")
            console.clear()
        except KeyboardInterrupt:
            console.print("\n[yellow]Saindo...[/yellow]")
            break
        except Exception as e:
            show_error(e)
            break

def run_single_execution(args):
    setup_logger(args.source_playlist)
    try:
        run_organizer(args)
    except Exception as e:
        show_error(e)

def run_interactive_wizard(args):
    yt_client = YTMusicClient()
    with console.status("[bold green]Buscando suas playlists..."):
        playlists = yt_client.get_user_playlists()

    if not playlists: return None

    playlist_choices = [questionary.Choice("🚪 Sair", value="EXIT"), "LM (Músicas Curtidas)"] + list(playlists.keys())
    selected = questionary.select("1. Playlist de origem?", choices=playlist_choices, qmark="🎵", pointer="▶", style=custom_theme).ask()
    if not selected or selected == "EXIT": return None
    
    args.source_playlist = "LM" if selected == "LM (Músicas Curtidas)" else playlists[selected]
    args.source_playlist_name = selected # Salva o nome amigável
    
    strat_choices = [
        questionary.Choice("🎸 Gênero", value="genre"),
        questionary.Choice("🌈 Vibe", value="vibe"),
        questionary.Choice("⏰ Momento", value="time"),
        questionary.Choice("❄️ Estação", value="season")
    ]
    args.strategy = questionary.select("2. Estratégia?", choices=strat_choices, qmark="🎵", pointer="▶", style=custom_theme).ask()
    
    args.limit = None
    args.since = None
    limit_mode = questionary.select("3. Limites?", choices=["Tudo", "Quantidade", "Data"], qmark="🎵", pointer="▶", style=custom_theme).ask()
    if limit_mode == "Quantidade":
        args.limit = int(questionary.text("Quantas?", default="50", qmark="🎵", style=custom_theme).ask())
    elif limit_mode == "Data":
        args.since = questionary.text("Data (DD-MM-AAAA)?", default="01-01-2024", qmark="🎵", style=custom_theme).ask()

    args.dry_run = False
    return args

def run_organizer(args):
    from datetime import datetime
    pname = getattr(args, 'source_playlist_name', args.source_playlist)
    console.print(f"[cyan]Lendo {pname} e gerando Panorama Global...[/cyan]")
    
    yt_music_client = YTMusicClient()
    tracks = yt_music_client.get_playlist_items(args.source_playlist)
    
    if args.since:
        try:
            since_date = datetime.strptime(args.since, "%d-%m-%Y")
            tracks = [t for t in tracks if t.get('liked_at') and datetime.fromisoformat(t['liked_at'].replace("Z", "")) >= since_date]
        except: pass
    
    if args.limit: tracks = tracks[:args.limit]
    if not tracks: return console.print("[yellow]Nenhuma música encontrada.[/yellow]")

    # Pre-flight check do Ollama
    try:
        import ollama
        ollama.list()
    except Exception:
        raise Exception("O motor de Inteligência Artificial (Ollama) não está respondendo.")
        
    classifier = MusicClassifier(args.model)
    
    from core.cache import CacheManager
    cache = CacheManager.load_cache()
    
    # Registra o Shutdown Handler
    handler = ShutdownHandler(CacheManager, cache)
    
    # 1. ANÁLISE INDIVIDUAL PROFUNDA (BATCH)
    with Progress(SpinnerColumn("bouncingBar", style="bold magenta"), TextColumn("[progress.description]{task.description}"), BarColumn(style="dim", complete_style="bold magenta"), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("[cyan]Análise Estratégica...", total=len(tracks))
        
        uncached_tracks = []
        for track in tracks:
            cache_key = f"{track['id']}_{args.strategy}"
            if cache_key in cache:
                track['metadata'] = cache[cache_key]
                progress.advance(task)
            else:
                uncached_tracks.append(track)
                
        # Lotes Dinâmicos (Default: 15)
        batch_size = args.batch_size
        
        funny_messages = [
            "📻 Analisando DNA...", "🎧 Decifrando batidas...", "🚶 Mapeando vibes...",
            "🎸 Identificando solos...", "💿 Lendo sulcos...", "🎹 Escaneando timbres...",
            "🎤 Filtrando vocais...", "🥁 Medindo BPM...", "🎶 Sintetizando notas...",
            "🧠 Extraindo essência...", "🔮 Prevendo aura...", "🎛️ Ajustando frequências...",
            "🔥 Calculando energia...", "🌊 Surfando ondas...", "🎷 Traduzindo sopros..."
        ]
        
        for i in range(0, len(uncached_tracks), batch_size):
            batch = uncached_tracks[i:i+batch_size]
            current_msg = random.choice(funny_messages)
            
            random_track = random.choice(batch)
            display_title = (random_track['title'][:30] + '..') if len(random_track['title']) > 30 else random_track['title']
            
            progress.update(task, description=f"[bold magenta]▂▃▅[/] [cyan]{current_msg}[/] [dim]| 🎵 {display_title}[/dim]")
            
            resultados = classifier.batch_deep_classify(batch, args.strategy)
            
            for track in batch:
                cache_key = f"{track['id']}_{args.strategy}"
                track['metadata'] = resultados.get(track['id'], "não-musical")
                cache[cache_key] = track['metadata']
                progress.advance(task)
                
            CacheManager.save_cache(cache)

    musical_tracks = [t for t in tracks if isinstance(t['metadata'], dict)]
    discarded_count = len(tracks) - len(musical_tracks)

    # 2. PANORAMA GLOBAL E ESTRATÉGIA (ANIMAÇÃO GRANDE)
    from rich.live import Live
    from rich.align import Align
    from rich.console import Group
    from rich.text import Text
    from rich.spinner import Spinner
    from rich.prompt import Confirm
    
    thinking_messages = [
        "🧠 MAPEANDO CONEXÕES NEURAIS...",
        "🧩 SINTETIZANDO PADRÕES MUSICAIS...",
        "🎨 ESCULPINDO PLAYLISTS TEMÁTICAS...",
        "⚖️ EQUILIBRANDO FLUXO DE ENERGIA...",
        "🚀 FINALIZANDO ARQUITETURA GLOBAL..."
    ]
    
    def get_thinking_panel(msg_idx):
        return Group(
            "\n\n",
            Align.center(
                Panel(
                    Group("\n", Align.center(Spinner("dots12", style="bold magenta", speed=1.5)), "\n",
                          Align.center(Text(thinking_messages[msg_idx], style="bold cyan pulse")), "\n"),
                    title="[bold magenta] CÉREBRO DIGITAL EM AÇÃO [/]",
                    subtitle="[dim]Processando Panorama Global da sua Biblioteca[/dim]",
                    border_style="magenta", width=60, padding=(1, 2)
                ), vertical="middle"
            ),
            "\n\n"
        )

    existing_playlists = yt_music_client.get_user_playlists()

    # Evitar mesclar na playlist de origem
    existing_playlists_for_ai = existing_playlists.copy()
    keys_to_delete = [k for k, v in existing_playlists_for_ai.items() if v == args.source_playlist]
    for k in keys_to_delete:
        del existing_playlists_for_ai[k]

    with Live(get_thinking_panel(0), refresh_per_second=10) as live:
        all_metadata = [t['metadata'] for t in musical_tracks]
        for i in range(3):
            live.update(get_thinking_panel(i))
            time.sleep(0.8)
        plano = classifier.generate_global_strategy(all_metadata, existing_playlists_for_ai, args.strategy)
        live.update(get_thinking_panel(4))
        time.sleep(0.5)

    if not plano: return console.print("[red]Falha ao gerar plano de organização.[/red]")

    # 3. MAPEAMENTO INICIAL (Para filtrar alucinações da IA e mostrar panorama)
    # Vinculamos as músicas aos grupos do plano ANTES de perguntar ao usuário
    for track in musical_tracks:
        m = track['metadata']
        best_p = plano[0]
        max_hits = -1
        for p in plano:
            hits = 0
            criterios = [c.lower() for c in p['criterios']]
            tags = [m['genero_base'].lower(), m['sub_genero'].lower(), m['vibe'].lower()]
            for tag in tags:
                if any(tag in crit for crit in criterios): hits += 1
            if hits > max_hits:
                max_hits = hits
                best_p = p
        track['temp_group'] = best_p['nome_grupo']

    # Filtrar apenas grupos que realmente possuem músicas
    used_groups = {t['temp_group'] for t in musical_tracks}
    plano_filtrado = [p for p in plano if p['nome_grupo'] in used_groups]

    # --- TABELA DE PANORAMA INICIAL ---
    summary_table = Table(title="📋 Panorama de Organização Sugerido", box=box.DOUBLE_EDGE)
    summary_table.add_column("Grupo Musical", style="magenta")
    summary_table.add_column("Destino Sugerido", style="cyan")
    summary_table.add_column("Ação", style="bold")
    summary_table.add_column("Qtd", justify="center")
    
    counts = {}
    for t in musical_tracks: counts[t['temp_group']] = counts.get(t['temp_group'], 0) + 1
    
    for p in plano_filtrado:
        acao = "[green]Mesclar[/green]" if p.get('is_merge') else "[yellow]Criar Nova[/yellow]"
        summary_table.add_row(p['nome_grupo'], p['target_playlist'], acao, str(counts.get(p['nome_grupo'], 0)))
    
    console.print(summary_table)

    # 4. VALIDAÇÃO DE MERGES (Perguntar um por um baseado na tabela acima)
    final_mapping = {} # nome_grupo -> playlist_final
    console.print("\n[bold cyan]🤖 Validação de Mesclagens (Merges):[/bold cyan]")
    
    for p in plano_filtrado:
        if p.get('is_merge'):
            ans = questionary.select(
                f"A IA sugere mesclar '{p['nome_grupo']}' em '{p['target_playlist']}'. O que deseja fazer?",
                choices=[
                    "✅ Sim, aceitar mesclagem",
                    "✨ Não, criar como NOVA playlist",
                    "🔄 Não, escolher OUTRA playlist existente"
                ],
                qmark="🎵", pointer="▶", style=custom_theme
            ).ask()
            
            if ans == "✅ Sim, aceitar mesclagem":
                final_mapping[p['nome_grupo']] = p['target_playlist']
            elif ans == "✨ Não, criar como NOVA playlist":
                new_name = f"{p['nome_grupo'].capitalize()} (Auto)"
                final_mapping[p['nome_grupo']] = new_name
                p['target_playlist'] = new_name
                p['is_merge'] = False
            else:
                outra = questionary.select("Escolha a playlist destino:", choices=list(existing_playlists.keys()), qmark="🎵", pointer="▶", style=custom_theme).ask()
                final_mapping[p['nome_grupo']] = outra
                p['target_playlist'] = outra
        else:
            final_mapping[p['nome_grupo']] = p['target_playlist']

    console.print("\n[bold cyan]📊 Panorama Final (Após Validações):[/bold cyan]")
    
    # Atribuição Final
    for track in musical_tracks:
        track['genre'] = final_mapping[track['temp_group']]

    from rich.tree import Tree
    tree = Tree("🎧 [bold cyan]Sua Nova Biblioteca Musical[/bold cyan]")
    
    playlists_tree = {}
    for track in musical_tracks:
        pl_name = track['genre']
        playlists_tree.setdefault(pl_name, []).append(track['title'])
        
    for pl_name, t_list in playlists_tree.items():
        branch = tree.add(f"💿 [bold magenta]{pl_name}[/bold magenta] [dim]({len(t_list)} músicas)[/dim]")
        for t in t_list[:4]:
            branch.add(f"🎵 [cyan]{t}[/cyan]")
        if len(t_list) > 4:
            branch.add(f"[dim]... e mais {len(t_list)-4} faixas ocultas[/dim]")
            
    console.print(Panel(tree, border_style="cyan", padding=(1, 2)))

    # Orçamento Estimado Dinâmico
    final_counts = {}
    for t in musical_tracks: final_counts[t['genre']] = final_counts.get(t['genre'], 0) + 1
    
    num_novas = sum(1 for gen in final_counts if gen not in existing_playlists)
    num_totais = len(final_counts)
    
    # Cálculo: (Músicas * 50) + (Novas Playlists * 50) + (Total Playlists * 1 para verificação)
    total_quota_est = (len(musical_tracks) * 50) + (num_novas * 50) + (num_totais * 1)
    
    console.print(f"\n[bold yellow]💰 Orçamento Estimado: ~{total_quota_est} unidades[/bold yellow]")
    if num_novas < num_totais:
        poupanca = (num_totais - num_novas) * 50
        console.print(f"[dim green]🍃 Economia por Merges: {poupanca} unidades salvas![/dim green]")
        
    check_quota_limit(total_quota_est, args)

    if not args.dry_run and not Confirm.ask("\n🚀 Deseja aplicar essa estratégia agora?"):
        args.dry_run = True

    # 4. EXECUÇÃO (Sincronização)
    youtube_client = YouTubeClient()
    logger = logging.getLogger("YTOrganizer")
    created, updated, real_quota = 0, 0, 0
    grouped = {}
    for t in musical_tracks:
        grouped.setdefault(t['genre'], []).append(t)

    logger.info(f"Iniciando sincronização de {len(musical_tracks)} músicas em {len(grouped)} playlists.")
    
    session_id = DatasetManager.init_execution(args.strategy)
    created_pids_this_session = []

    try:
        with Progress(SpinnerColumn("bouncingBar", style="bold magenta"), TextColumn("[progress.description]{task.description}"), BarColumn(style="dim", complete_style="bold green"), TaskProgressColumn(), console=console) as progress:
            sync_task = progress.add_task("[bold cyan]Iniciando Tape Deck...[/]", total=len(musical_tracks))
            
            for pname, items in grouped.items():
                pid = existing_playlists.get(pname)
                
                is_new = False
                if not pid and not args.dry_run:
                    progress.update(sync_task, description=f"[bold magenta]▶ TOCANDO AGORA:[/] [bold cyan]{pname}[/] [dim]||[/dim] [yellow]Criando playlist...[/]")
                    logger.info(f"Criando nova playlist: {pname}")
                    pid = youtube_client.create_playlist(pname)
                    if pid:
                        created += 1
                        is_new = True
                        created_pids_this_session.append(pid)
                    else:
                        raise Exception(f"Falha inrecuperável ao criar playlist {pname}")
                elif pid:
                    logger.info(f"Playlist existente encontrada: {pname} (ID: {pid})")
                    updated += 1

                if pid:
                    existing_ids = set() if is_new else youtube_client.get_playlist_items(pid)
                    logger.info(f"Playlist {pname} tem {len(existing_ids)} músicas. Adicionando novas...")
                    
                    for track in items:
                        display_title = (track['title'][:35] + '..') if len(track['title']) > 35 else track['title']
                        progress.update(sync_task, description=f"[bold magenta]▶ TOCANDO AGORA:[/] [bold cyan]{pname}[/] [dim]||[/dim] [green]{display_title}[/]")
                        
                        if track['id'] not in existing_ids and not CheckpointManager.is_synced(pid, track['id']):
                            logger.info(f"Enviando para '{pname}': {track['title']}")
                            if not args.dry_run: 
                                res = youtube_client.add_to_playlist(pid, track['id'])
                                if res is None:
                                    logger.error("Falha ao adicionar vídeo. Erro de API.")
                                    progress.update(sync_task, description=f"[bold red]Erro de API em {pname}[/bold red]")
                                else:
                                    CheckpointManager.add_synced_track(pid, track['id'])
                                    DatasetManager.update_execution(session_id, track['title'], track['artist'], pname, track['metadata'])
                        else:
                            logger.info(f"Já existe em '{pname}': {track['title']}")
                            if args.dry_run: DatasetManager.update_execution(session_id, track['title'], track['artist'], pname, track['metadata'])
                            
                        progress.advance(sync_task)
                elif args.dry_run:
                    for track in items:
                        display_title = (track['title'][:35] + '..') if len(track['title']) > 35 else track['title']
                        progress.update(sync_task, description=f"[dim cyan]▶ TOCANDO AGORA (DRY-RUN):[/] [bold cyan]{pname}[/] [dim]||[/dim] [green]{display_title}[/]")
                        logger.info(f"[Dry Run] Enviando para '{pname}': {track['title']}")
                        DatasetManager.update_execution(session_id, track['title'], track['artist'], pname, track['metadata'])
                        progress.advance(sync_task)
    except Exception as e:
        console.print(f"\n[bold red]Erro Crítico Detectado:[/] {e}. [yellow]Iniciando Rollback...[/yellow]")
        for c_pid in reversed(created_pids_this_session):
            try:
                youtube_client.youtube.playlists().delete(id=c_pid).execute()
                console.print(f"[green]Rollback: Playlist recém-criada (ID: {c_pid}) destruída.[/green]")
            except Exception as rb_e:
                console.print(f"[red]Falha ao reverter playlist {c_pid}: {rb_e}[/red]")
        raise e
        
    logger.info(f"Sincronização finalizada. Criadas: {created}, Atualizadas: {updated}")
    print_report(len(musical_tracks), len(grouped), created, updated, final_counts, discarded_count)
    
    if not args.dry_run:
        CheckpointManager.clear()
    DatasetManager.commit_execution(session_id)

if __name__ == "__main__":
    main()
