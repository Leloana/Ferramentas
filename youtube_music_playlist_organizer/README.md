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
- [Ollama](https://ollama.com/) instalado e rodando com um modelo disponível (ex: `gemma4:e4b` configurável no `.env`).
- Conta no Google Cloud com a YouTube Data API v3 ativada.

## 🚀 Instalação Rápida

1. **Clone o repositório**:
   ```bash
   git clone <este-repo>
   cd youtube_music_playlist_organizer
   ```

2. **Crie o ambiente virtual e instale as dependências**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configuração de API**:
   - Coloque seu arquivo `client-tv.json` (baixado do Google Cloud) na raiz do projeto.
   - Rode o instalador de autenticação inicial:
     ```powershell
     python setup_oauth.py
     ```

## 🎮 Como Usar

### O Assistente Musical (Menu Interativo)
Basta rodar o comando abaixo e você será guiado pela interface Neon do assistente:
```powershell
python main.py
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
    - `ytmusic_client.py`: Leitura de bibliotecas gratuitas pelo YTMusic.
    - `youtube_client.py`: Escrita/Modificações oficiais autenticadas no YouTube.
    - `quota_manager.py`: O cofre de contabilização da cota diária do YouTube.
    - `cache.py`: O armazenador temporal de análise para não sobrecarregar a IA nem a Cota.
- `logs/`: Logs avançados para auditoria das respostas da IA e da API em tempo real.

## 📜 Licença
MIT
