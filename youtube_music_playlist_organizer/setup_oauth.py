import os
import json
import webbrowser
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from ytmusicapi.auth.oauth.credentials import OAuthCredentials
from ytmusicapi.auth.oauth.token import RefreshingToken

console = Console()

def run_setup():
    console.print(Panel.fit(
        "[bold cyan]Configurador de Autenticação Premium (YouTube Music)[/bold cyan]",
        border_style="cyan"
    ))

    # 1. Carregar credenciais do JSON
    json_path = "client-tv.json"
    if not os.path.exists(json_path):
        console.print(f"[red]Erro: Arquivo '{json_path}' não encontrado.[/red]")
        return

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        key = 'installed' if 'installed' in data else 'web'
        client_id = data[key]['client_id']
        client_secret = data[key]['client_secret']
        credentials = OAuthCredentials(client_id, client_secret)

        # 2. Obter código de autorização
        code = credentials.get_code()
        url = f"{code['verification_url']}?user_code={code['user_code']}"

        # 3. Exibir instruções bonitas
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold magenta]PASSO 1:[/bold magenta]", f"Abra este link no seu navegador:\n[link={url}][underline cyan]{url}[/underline cyan][/link]")
        table.add_row("", "") # Espaçador
        table.add_row("[bold magenta]PASSO 2:[/bold magenta]", "Faça login com sua conta do YouTube.")
        table.add_row("[bold magenta]PASSO 3:[/bold magenta]", "Confirme a autorização do dispositivo.")
        table.add_row("", "") # Espaçador
        table.add_row("[bold magenta]PASSO 4:[/bold magenta]", "Volte aqui e pressione [bold green]ENTER[/bold green] para finalizar.")

        console.print(Panel(
            table,
            title="[bold yellow]Siga estas etapas para conectar sua conta[/bold yellow]",
            border_style="yellow",
            padding=(1, 2)
        ))

        # Tenta abrir o navegador automaticamente
        webbrowser.open(url)

        input("\nPressione ENTER após concluir o login no navegador...")

        # 4. Finalizar e salvar o token
        console.print("\n[grey]Verificando autorização com o Google...[/grey]")
        
        raw_token = credentials.token_from_code(code["device_code"])
        
        # Patch manual direto aqui também para evitar o erro anterior
        import dataclasses
        valid_fields = {f.name for f in dataclasses.fields(RefreshingToken)}
        filtered_token = {k: v for k, v in raw_token.items() if k in valid_fields}
        
        ref_token = RefreshingToken(credentials=credentials, **filtered_token)
        ref_token.update(ref_token.as_dict())
        
        # Salva o arquivo incluindo as credenciais necessárias para refresh
        token_data = ref_token.as_dict()
        token_data['client_id'] = client_id
        token_data['client_secret'] = client_secret

        with open("oauth.json", "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=4)

        console.print(Panel(
            "[bold green]✅ CONECTADO COM SUCESSO![/bold green]\n\nO arquivo [cyan]oauth.json[/cyan] foi criado.\nAgora você pode rodar o script principal.",
            border_style="green",
            padding=(1, 2)
        ))

    except Exception as e:
        error_text = str(e)
        msg = f"[bold red]Erro durante a configuração:[/bold red]\n\n{error_text}"
        console.print(Panel(msg, title="[bold red]FALHA[/bold red]", border_style="red"))

if __name__ == "__main__":
    run_setup()
