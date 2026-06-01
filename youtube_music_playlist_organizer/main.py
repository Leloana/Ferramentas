import argparse
import sys
import random
import logging
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import box
import signal
import atexit

from core.config import (
    OLLAMA_MODEL_DEFAULT, API_DAILY_LIMIT,
    COST_INSERT_PLAYLIST_ITEM, COST_CREATE_PLAYLIST, COST_LIST,
)
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
        genre_str = str(genre) if genre is not None else "Desconhecido"
        genre_table.add_row(genre_str.ljust(15), f"→ {count} músicas")

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
        dica = "\n\n💡 [bold yellow]DICA:[/bold yellow] Confira o [cyan].env[/cyan] (YOUTUBE_CLIENT_ID/SECRET) e apague o [cyan]token.json[/cyan] para refazer o login do Google na próxima execução."
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
    parser.add_argument("--max-playlists", type=int, help="Número máximo de playlists criadas")
    parser.add_argument("--auto", action="store_true", help="Aceita os merges sugeridos pela IA e aplica sem confirmação (uso periódico/agendado)")
    
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

    max_playlists_input = questionary.text("4. Limite de playlists a criar (Deixe vazio para IA decidir):", qmark="🎵", style=custom_theme).ask()
    if max_playlists_input and max_playlists_input.isdigit():
        args.max_playlists = int(max_playlists_input)
    else:
        args.max_playlists = None

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

    # Pre-flight check do Ollama: serviço no ar + modelo realmente instalado
    try:
        import ollama
        installed = ollama.list()
    except Exception:
        raise Exception("O motor de Inteligência Artificial (Ollama) não está respondendo.")

    models_list = getattr(installed, 'models', None)
    if models_list is None and isinstance(installed, dict):
        models_list = installed.get('models', [])
    names = []
    for m in (models_list or []):
        n = getattr(m, 'model', None) or getattr(m, 'name', None)
        if n is None and isinstance(m, dict):
            n = m.get('model') or m.get('name')
        if n:
            names.append(n)
    base = args.model.split(':')[0]
    if names and not any(n == args.model or n.split(':')[0] == base for n in names):
        raise Exception(
            f"Modelo '{args.model}' não encontrado no Ollama.\n"
            f"Modelos instalados: {', '.join(names) or '(nenhum)'}\n"
            f"Baixe com: ollama pull {args.model}  (ou use --model <nome instalado>)"
        )
        
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

    # 2. PANORAMA GLOBAL E ESTRATÉGIA
    from rich.prompt import Confirm
    logger = logging.getLogger("YTOrganizer")

    existing_playlists = yt_music_client.get_user_playlists()

    # Evitar mesclar na playlist de origem
    existing_playlists_for_ai = existing_playlists.copy()
    keys_to_delete = [k for k, v in existing_playlists_for_ai.items() if v == args.source_playlist]
    for k in keys_to_delete:
        del existing_playlists_for_ai[k]

    with console.status("[bold magenta]🧠 Gerando panorama global da sua biblioteca...", spinner="dots12"):
        all_metadata = [t['metadata'] for t in musical_tracks]
        plano = classifier.generate_global_strategy(all_metadata, existing_playlists_for_ai, args.strategy, getattr(args, 'max_playlists', None))

    if not plano: return console.print("[red]Falha ao gerar plano de organização.[/red]")

    # 3. ATRIBUIÇÃO FAIXA→GRUPO (a IA coloca cada música no grupo ideal do plano)
    def _fallback_group(m):
        """Reserva por substring caso a IA não atribua a faixa. Retorna (grupo, hits)."""
        best, max_hits = plano[0]['nome_grupo'], -1
        for p in plano:
            criterios = [c.lower() for c in p.get('criterios', [])]
            tags = [str(m.get('genero_base', '')).lower(), str(m.get('sub_genero', '')).lower(), str(m.get('vibe', '')).lower()]
            hits = sum(1 for tag in tags if tag and any(tag in crit for crit in criterios))
            if hits > max_hits:
                max_hits, best = hits, p['nome_grupo']
        return best, max_hits

    with Progress(SpinnerColumn("bouncingBar", style="bold magenta"), TextColumn("[progress.description]{task.description}"), BarColumn(style="dim", complete_style="bold magenta"), TaskProgressColumn(), console=console) as progress:
        atask = progress.add_task("[cyan]🎯 Encaixando cada faixa no grupo ideal...", total=len(musical_tracks))
        assignments = classifier.assign_to_groups(musical_tracks, plano, args.strategy, progress_cb=lambda n: progress.advance(atask, n))

    fallback_used = 0
    for track in musical_tracks:
        g = assignments.get(track['id'])
        if not g:
            g, hits = _fallback_group(track['metadata'])
            fallback_used += 1
            logger.warning(f"Faixa sem atribuição da IA, usando reserva (hits={hits}): {track['title']} → {g}")
        track['temp_group'] = g
    if fallback_used:
        console.print(f"[dim]ℹ️ {fallback_used} faixa(s) atribuída(s) por heurística de reserva.[/dim]")

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

    # 4. VALIDAÇÃO DE MERGES (interativa; ou automática com --auto p/ uso periódico)
    auto = getattr(args, 'auto', False)
    final_mapping = {} # nome_grupo -> playlist_final
    if not auto:
        console.print("\n[bold cyan]🤖 Validação de Mesclagens (Merges):[/bold cyan]")

    for p in plano_filtrado:
        # Proteção: merge para playlist inexistente (alucinação da IA) → vira NOVA
        # com nome limpo (o próprio nome do grupo, já coerente com a estratégia).
        if p.get('is_merge') and p.get('target_playlist') not in existing_playlists:
            p['is_merge'] = False
            p['target_playlist'] = p['nome_grupo']

        if p.get('is_merge') and not auto:
            ans = questionary.select(
                f"A IA sugere mesclar '{p['nome_grupo']}' em '{p['target_playlist']}'. O que deseja fazer?",
                choices=[
                    "✅ Sim, aceitar mesclagem",
                    "✨ Não, criar como NOVA playlist",
                    "🔄 Não, escolher OUTRA playlist existente"
                ],
                qmark="🎵", pointer="▶", style=custom_theme
            ).ask()

            if ans == "✨ Não, criar como NOVA playlist":
                final_mapping[p['nome_grupo']] = p['nome_grupo']
                p['target_playlist'] = p['nome_grupo']
                p['is_merge'] = False
            elif ans == "🔄 Não, escolher OUTRA playlist existente":
                outra = questionary.select("Escolha a playlist destino:", choices=list(existing_playlists.keys()), qmark="🎵", pointer="▶", style=custom_theme).ask()
                final_mapping[p['nome_grupo']] = outra
                p['target_playlist'] = outra
            else:
                # Default (inclui "aceitar"): mescla na sugestão da IA
                final_mapping[p['nome_grupo']] = p['target_playlist']
        else:
            # Não-merge, ou modo --auto (aceita a sugestão da IA como está)
            final_mapping[p['nome_grupo']] = p['target_playlist']

    console.print("\n[bold cyan]📊 Panorama Final (Após Validações):[/bold cyan]")
    
    # Atribuição Final
    for track in musical_tracks:
        genre_val = final_mapping.get(track['temp_group'], "Mistura Musical")
        track['genre'] = genre_val if genre_val is not None else "Mistura Musical"

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
    
    # Estimativa de cota da fase de escrita (conservadora):
    #  - cada música inserida custa COST_INSERT_PLAYLIST_ITEM
    #  - cada playlist nova custa COST_CREATE_PLAYLIST
    #  - 1 list por playlist para verificar duplicatas (COST_LIST)
    # (a leitura/análise já foi debitada ao vivo no QuotaManager antes daqui)
    total_quota_est = (
        len(musical_tracks) * COST_INSERT_PLAYLIST_ITEM
        + num_novas * COST_CREATE_PLAYLIST
        + num_totais * COST_LIST
    )
    
    console.print(f"\n[bold yellow]💰 Orçamento Estimado: ~{total_quota_est} unidades[/bold yellow]")
    if num_novas < num_totais:
        poupanca = (num_totais - num_novas) * COST_CREATE_PLAYLIST
        console.print(f"[dim green]🍃 Economia por Merges: {poupanca} unidades salvas![/dim green]")

    check_quota_limit(total_quota_est, args)

    if not args.dry_run and not auto and not Confirm.ask("\n🚀 Deseja aplicar essa estratégia agora?"):
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
                youtube_client.delete_playlist(c_pid)
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
