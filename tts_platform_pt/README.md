# 🗣️ Plataforma de TTS em Português

Servidor web local (FastAPI) que sintetiza fala em português usando o **XTTS-v2**
([`coqui/XTTS-v2`](https://huggingface.co/coqui/XTTS-v2), modelo multilíngue com
clonagem de voz zero-shot), com um passo opcional de normalização do texto via
**Ollama** local antes da síntese (expande siglas, abreviações e números, ajusta
pontuação para soar mais natural).

## Como rodar

### Setup inicial (só na primeira vez)

```powershell
cd C:\Users\mf827\Documents\Ferramentas\tts_platform_pt
python -m venv venv
C:\Users\mf827\Documents\Ferramentas\tts_platform_pt\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Rodar o servidor (dia a dia)

```powershell
C:\Users\mf827\Documents\Ferramentas\tts_platform_pt\venv\Scripts\uvicorn.exe server.main:app --app-dir C:\Users\mf827\Documents\Ferramentas\tts_platform_pt --reload --port 8011
```

Abra `http://127.0.0.1:8011/` no navegador.

### Pré-requisitos

- **Ollama** (opcional) aberto localmente com o modelo `qwen3:0.6b` baixado
  (`ollama pull qwen3:0.6b`) — ou ajuste `OLLAMA_MODEL` em `server/config.py`.
  A caixa "Normalizar texto com IA" no front é o toggle real: desmarcada, o
  Ollama nunca é chamado, mesmo que esteja rodando. Se estiver marcada mas o
  Ollama não responder, a normalização falha silenciosamente e o texto
  original é usado — a síntese continua funcionando.
- **GPU NVIDIA (CUDA)** recomendada. Sem GPU, o servidor cai automaticamente
  para CPU, mas a síntese com XTTS-v2 fica bem mais lenta.
- **Internet na primeira execução**: o checkpoint do XTTS-v2 (~1.8GB) é baixado
  automaticamente do Hugging Face no primeiro request de síntese e fica em
  cache local (fora deste repositório).
- Ao carregar o modelo pela primeira vez, o código aceita programaticamente a
  licença **Coqui Public Model License (CPML)** do XTTS-v2 (via variável de
  ambiente `COQUI_TOS_AGREED=1`, setada em `server/engine/tts_engine.py`) para
  não travar em um prompt interativo no terminal. A CPML permite uso não
  comercial livremente; uso comercial tem condições próprias — vale ler os
  termos em https://coqui.ai/cpml antes de qualquer uso além de testes locais.

### VRAM: Ollama + XTTS-v2 na mesma GPU

Testado numa RTX 4070 (12GB): o que domina o consumo de VRAM do Ollama é o
**tamanho do contexto (`num_ctx`)**, não a contagem de parâmetros do modelo —
o padrão do Qwen3 (`num_ctx=40960`) sozinho já consome ~5GB.

Por isso o `num_ctx` **não é fixo**: a cada chamada, `text_preprocessor.py`
mede a VRAM livre no momento (via `nvidia-smi`) e escolhe o maior patamar de
contexto que cabe, reservando espaço pro XTTS-v2 (`OLLAMA_XTTS_RESERVE_MB` em
`server/config.py`). Patamares medidos nesta máquina: `4096`→~1GB,
`8192`→~1.5GB, `16384`→~2.5GB, `32768`→~4.4GB. **Se não sobrar VRAM nem para
o menor patamar, a normalização é pulada automaticamente** — o áudio é
gerado sem ela, e a resposta/UI mostra um aviso explicando o motivo, em vez
de arriscar um erro de memória na GPU.

Isso usa `nvidia-smi`, não `torch.cuda.mem_get_info()`: no Windows (driver
WDDM), a visão do PyTorch sobre VRAM livre não contabiliza corretamente o que
outros processos (como o Ollama) estão usando — chegou a reportar 11GB livres
quando só havia 4GB de verdade nos testes. Se trocar `OLLAMA_MODEL` por um
modelo maior, meça de novo com `ollama ps` (mostra o tamanho real em VRAM,
incluindo o contexto) antes de assumir que os patamares em `config.py` ainda
fazem sentido.

## Uso

1. Digite o texto na caixa. Se "Normalizar" estiver marcado, aparece uma
   estimativa aproximada de tokens (~4 caracteres por token) comparada ao
   `num_ctx` configurado do Ollama, pra saber se o texto cabe no contexto.
2. Escolha uma voz embutida do XTTS-v2, ou envie um `.wav` de 6-30s de fala
   limpa para clonar uma voz nova (fica disponível na lista como "🎙️ ... (clonada)").
3. Marque/desmarque "Normalizar texto com IA" para usar ou não o pré-processamento
   via Ollama — desmarcado, o Ollama nunca é chamado.
4. Clique em "Gerar áudio" — o resultado toca automaticamente e pode ser baixado.

## Endpoints

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/voices` | Lista vozes embutidas do XTTS-v2 e vozes clonadas |
| `POST` | `/api/voices` | Upload de `.wav` de referência para clonagem |
| `POST` | `/api/synthesize` | `{texto, voice_id, language, normalizar}` → `{audio_url, texto_usado, aviso_normalizacao}` |
