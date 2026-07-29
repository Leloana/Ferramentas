# 🗣️ Plataforma de TTS em Português

Servidor web local (FastAPI) que sintetiza fala em português usando o **XTTS-v2**
([`coqui/XTTS-v2`](https://huggingface.co/coqui/XTTS-v2), modelo multilíngue com
clonagem de voz zero-shot), com um passo opcional de normalização do texto via
**Ollama** local antes da síntese (expande siglas, abreviações e números, ajusta
pontuação para soar mais natural).

## Como rodar

```powershell
cd tts_platform_pt
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

uvicorn server.main:app --reload --port 8010
```

Abra `http://127.0.0.1:8010/` no navegador.

### Pré-requisitos

- **Ollama** aberto localmente com o modelo `gemma3n:e4b` baixado (ou ajuste
  `OLLAMA_MODEL` em `server/config.py`). Se o Ollama não estiver disponível, a
  normalização falha silenciosamente e o texto original é usado — a síntese
  continua funcionando.
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

## Uso

1. Digite o texto na caixa.
2. Escolha uma voz embutida do XTTS-v2, ou envie um `.wav` de 6-30s de fala
   limpa para clonar uma voz nova (fica disponível na lista como "🎙️ ... (clonada)").
3. Marque/desmarque "Normalizar texto com IA" para usar ou não o pré-processamento
   via Ollama.
4. Clique em "Gerar áudio" — o resultado toca automaticamente e pode ser baixado.

## Endpoints

| Método | Rota | Descrição |
| --- | --- | --- |
| `GET` | `/api/voices` | Lista vozes embutidas do XTTS-v2 e vozes clonadas |
| `POST` | `/api/voices` | Upload de `.wav` de referência para clonagem |
| `POST` | `/api/synthesize` | `{texto, voice_id, language, normalizar}` → `{audio_url, texto_usado}` |
