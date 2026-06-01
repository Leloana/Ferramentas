# ▶ P L A Y L I S T   O R G A N I Z E R (AI Powered)

Um organizador inteligente e visualmente deslumbrante para sua biblioteca do YouTube Music. Com interface imersiva inspirada em players cyberpunk, o sistema utiliza Inteligência Artificial local para analisar, categorizar e gerenciar suas músicas.

## ✨ Novidades da Versão 3.0 (Enterprise)

- **⚡ Processamento em Lote (Batching)**: A IA agora processa músicas em blocos, reduzindo drasticamente o tempo de mapeamento inicial.
- **💾 Sistema de Cache Nativo**: Músicas mapeadas são salvas em um cache interno. Se a cota acabar hoje, amanhã a ferramenta continua imediatamente de onde parou.
- **📊 Gerenciamento Restrito de Cotas**: Monitoramento minucioso do limite diário (10.000 unidades) do YouTube Data API v3 para evitar bloqueios inesperados.
- **🎨 Identidade Visual Cyberpunk**: Barra de progresso com Equalizadores, painel ASCII retrô, cursores personalizados (▶) e visuais interativos que rementem a apps nativos de áudio (incluindo Widget de "Tocando Agora").
- **🌳 Arquitetura em Árvore**: Visualização final em `Tree` hierárquico antes de fazer modificações na sua conta, garantindo transparência total da ação.
- **🌈 Curadoria Contextual Avançada**: A LLM agora ajusta a forma de pensar baseada na sua estratégia (Gênero, Vibe, Estação do ano ou Momento) e prioriza abstrações baseadas em sentimentos e emojis (ex: `🌧️ Melancolia Profunda`).

## 🛠️ Pré-requisitos
- Python 3.10+
- [Ollama](https://ollama.com/) instalado e rodando com um modelo disponível (padrão: `gemma3n:e4b`, configurável via `--model`). Baixe com `ollama pull gemma3n:e4b`. **IMPORTANTE:** Certifique-se de que o aplicativo do Ollama está aberto no seu PC antes de rodar o projeto.

## 🚀 Como Obter as Credenciais do Google

Para que o script funcione, você precisa autorizá-lo a ler e editar suas playlists via **YouTube Data API v3**:

1. **Ative a API:** Acesse [Biblioteca de APIs - YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com) e clique em **Ativar**.
2. **Crie a Credencial OAuth:**
   - Acesse a aba de [Credenciais](https://console.cloud.google.com/apis/credentials).
   - Clique em **+ CRIAR CREDENCIAIS** > **ID do cliente OAuth**.
   - Tipo de Aplicativo: selecione **Aplicativo para computador (Desktop app)**.
   - Clique em Criar e **anote o Client ID e o Client Secret** (ou baixe o JSON).
3. **Libere o Acesso ao seu Email:**
   - Acesse a aba de [Tela de permissão OAuth (Audience)](https://console.cloud.google.com/auth/audience).
   - Em "Test users" (Usuários de teste), adicione o **e-mail exato da sua conta** do YouTube.

## 📦 Instalação Rápida

1. **Clone o repositório e crie o ambiente**:
   ```powershell
   git clone <este-repo>
   cd youtube_music_playlist_organizer
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure o `.env`**:
   Crie um arquivo `.env` na raiz do projeto com o Client ID e Secret do passo anterior:
   ```env
   YOUTUBE_CLIENT_ID=seu_client_id
   YOUTUBE_CLIENT_SECRET=seu_client_secret
   ```

3. **Primeiro login (gera `token.json`)**:
   Na primeira execução do `main.py`, um navegador abrirá automaticamente para você
   autorizar o acesso. O token é salvo em `token.json` e renovado sozinho nas próximas
   vezes — você só faz isso uma vez.

## 🎮 Como Usar

### O Assistente Musical (Menu Interativo)
Basta rodar o comando abaixo e você será guiado pela interface Neon do assistente:
```powershell
python main.py
```

### Execução periódica / agendada (sem teclado)
Para rodar de tempos em tempos sobre as Músicas Curtidas sem precisar confirmar nada,
use `--auto` (aceita os merges sugeridos pela IA e aplica direto). Reexecutar é seguro:
músicas já presentes nas playlists não são reenviadas (não gasta cota à toa).
```powershell
python main.py --source-playlist LM --strategy vibe --auto
```

### O Fluxo Completo:
1. **Origem:** Selecione qual playlist da sua conta será usada como "molde" (ex: "LM" para Músicas Curtidas).
2. **Estratégia:** Diga se a IA vai separar as músicas por Gênero, Vibe, Momento ou Estação.
3. **Limites:** Escolha analisar tudo ou estabeleça limites (quantidade ou após uma data específica).
4. **Análise IA (Lote):** O Equalizador exibirá o processamento rápido.
5. **Validação de Mesclagem:** A IA sugere "Merges" entre as músicas e playlists pré-existentes. Você pode aceitar, negar criando uma nova, ou selecionar um destino à força.
6. **Tape Deck (Sincronização):** Finaliza o fluxo aplicando a estratégia real-time na sua conta do YouTube, gerenciando os seus limites diários e informando o seu orçamento estimado.

## 📂 Estrutura Principal
- `main.py`: Ponto de entrada, interface gráfica (CLI) com biblioteca `rich` e `questionary`.
- `core/`:
    - `classifier.py`: O cérebro local que instrui o Ollama (Lotes, Prompts abstratos).
    - `ytmusic_client.py`: Leitura das faixas e do pré-filtro (via YouTube Data API v3 oficial).
    - `youtube_client.py`: Escrita/Modificações oficiais autenticadas no YouTube.
    - `auth.py`: Autenticação OAuth2 (gera/renova o `token.json` a partir do `.env`).
    - `config.py`: Modelo do Ollama, custos de cota, pré-filtro e teto de leitura.
    - `quota_manager.py`: O cofre de contabilização da cota diária do YouTube.
    - `cache.py`: O armazenador temporal de análise para não sobrecarregar a IA nem a Cota.
- `logs/`: Logs avançados para auditoria das respostas da IA e da API em tempo real.

## 📜 Licença
MIT
