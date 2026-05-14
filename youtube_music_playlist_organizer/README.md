# YouTube Music Playlist Organizer

Um script CLI em Python que automatiza a organização das suas playlists do YouTube Music. Ele lê as músicas de uma playlist de origem, classifica cada uma delas por gênero utilizando inteligência artificial local (Ollama) e, em seguida, as distribui em novas playlists separadas por gênero diretamente na sua conta do YouTube.

Tudo isso feito com relatórios visuais maravilhosos pelo terminal.

## Funcionalidades

- Extração de metadados ricos (Artista, Álbum, Título separados) do YT Music.
- Classificação 100% gratuita, sem API Keys externas de IA, utilizando um modelo LLM rodando localmente na sua máquina via [Ollama](https://ollama.com/).
- De-duplicação e checagem para não adicionar músicas que já estão em suas playlists de destino.
- Relatório visual final do processamento (com a biblioteca `rich`).
- Controle consciente de Quotas da Google API Data v3 para não exceder limites de inserção e listagem.

## Pré-requisitos

1. Python 3.8+
2. [Ollama](https://ollama.com/) instalado em sua máquina e o modelo alvo baixado.
   * Por padrão, é utilizado o modelo `gemma4:e4b`, mas você pode usar o `llama3`, `mistral`, etc., mudando a tag de configuração ou via terminal.
   * Se usar o padrão do plano, rode no terminal: `ollama run gemma4:e4b`
3. Um projeto Google Cloud Desktop habilitado para usar a **YouTube Data API v3** para obter seu *Client ID* e *Client Secret*.

## Setup Inicial

1. **Instale as dependências do projeto:**

```bash
pip install -r requirements.txt
```

2. **Configure suas variáveis de ambiente:**

Substitua as credenciais de `YOUTUBE_CLIENT_ID` e `YOUTUBE_CLIENT_SECRET` pelo seu app do [Google Cloud Console](https://console.cloud.google.com/):

Arquivo `.env`:
```env
YOUTUBE_CLIENT_ID=seu_client_id_aqui
YOUTUBE_CLIENT_SECRET=seu_client_secret_aqui
```

3. **Gere o token do YT Music API (Leitura)**

Você precisa gerar o arquivo `oauth.json` de autorização de leitura da biblioteca não-oficial `ytmusicapi`. Execute no seu terminal:

```bash
ytmusicapi oauth
```
Siga os passos na tela e cole os headers de autenticação conforme a ferramenta instruir (ele usará o navegador para capturar seu cookie de sessão do YT Music).

## Como Usar

Com as credenciais montadas (e o Ollama rodando localmente em `localhost:11434`), execute o script principal usando o seu terminal:

### Sintaxe Básica

```bash
python main.py --source-playlist <ID_DA_PLAYLIST>
```
* **ID_DA_PLAYLIST**: Trata-se daquele código maluco no final da URL da sua playlist original (ex: `PLxxx...`). 
* **Para organizar Músicas Curtidas**: Passe `LM` como playlist ID (`python main.py --source-playlist LM`).

### Flag de Simulação (Dry-Run)

Se você quiser testar as classificações e ver o painel final **sem de fato fazer nenhuma alteração** nas suas playlists do YouTube (evitando gastos de quota ou de alterar algo não desejado), use `--dry-run`:

```bash
python main.py --source-playlist <ID_DA_PLAYLIST> --dry-run
```

### Escolher o modelo de IA

Para mudar o modelo de inteligência artificial durante a execução, use o argumento `--model`:

```bash
python main.py --source-playlist LM --model llama3
```

*(Lembre-se de baixar o modelo antes via `ollama pull llama3`)*

## Informações Adicionais (Rate Limits da API)

Ao utilizar a API oficial do YouTube (Google API Data v3) para criar as playlists e salvar as músicas, tenha em mente as seguintes quotas do Google Cloud (Geralmente 10.000 unidades grátis por dia):

- **Listar Playlists e Itens**: 1 Unidade
- **Criar Playlist**: 50 Unidades
- **Inserir música na playlist**: 50 Unidades

O painel de processamento no final da CLI mostrará aproximadamente as unidades de API usadas durante a sua requisição para que você possa controlar esse uso de perto!
