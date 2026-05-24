# ⚠️ DEPRECATED - Original MVP Plan

> [!WARNING]
> **ESTE DOCUMENTO ESTÁ DEPRECADO / DEPRECATED**
> Este era o plano original para a criação do MVP do Karaokê. A estrutura descrita aqui (por exemplo, um arquivo `main.py` contendo toda a lógica) é obsoleta e foi substituída por uma arquitetura modularizada e de alta performance.
> Para a documentação atual do sistema, consulte:
> - [Guia do Projeto (PROJECT_GUIDE.md)](../guides/PROJECT_GUIDE.md)
> - [Manual de Arquitetura (ARCHITECTURE.md)](../architecture/ARCHITECTURE.md)

---

# Karaoke MVP — Prompt de Implementação

Crie um MVP de um sistema de karaoke local em Python onde o servidor roda no PC e o cliente é acessado via browser na mesma rede.

## Visão geral

O servidor Python processa tudo. O cliente (browser) captura o áudio do microfone e envia via WebSocket. O servidor acumula o áudio por segmento da música, transcreve com Whisper ao fim de cada segmento, compara com a letra esperada e devolve a pontuação. O feedback visual de destaque de palavras é controlado inteiramente pelo cliente usando `audio.currentTime`.

O backing track é apenas instrumental (sem vocal), portanto não há risco de o STT transcrever a música em vez da voz do jogador. Fone de ouvido não é necessário.

---

## Setup do ambiente

Crie um venv Python e instale as dependências:

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install fastapi "uvicorn[standard]" faster-whisper rapidfuzz numpy pydub python-multipart scipy
```

---

## Ferramentas utilizadas

- **FastAPI** — servidor HTTP + WebSocket
- **uvicorn** — ASGI server para rodar o FastAPI
- **faster-whisper** — transcrição de áudio (modelo medium por padrão, roda local na GPU; trocar para large-v3 se VRAM permitir)
- **rapidfuzz** — fuzzy matching entre letra transcrita e esperada
- **numpy** — manipulação de chunks de áudio PCM para passar direto ao Whisper
- **pydub** — pré-processamento de áudio apenas no script offline prepare_song.py
- **scipy** — resample de áudio no servidor de qualquer sample rate para 16kHz

---

## HTTPS na rede local

Navegadores modernos bloqueiam `getUserMedia` em conexões HTTP fora de `localhost`. O servidor deve rodar com HTTPS.

Gere um certificado autoassinado com openssl:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=192.168.1.X"
```

Substitua `192.168.1.X` pelo IP real do PC na rede local.

Rode o uvicorn com SSL:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile ./key.pem --ssl-certfile ./cert.pem
```

O cliente acessa via `https://192.168.1.X:8000`. O browser vai exibir um aviso de certificado não confiável — o usuário deve aceitar manualmente uma vez. Isso é esperado e suficiente para uso local.

---

## CORS

Adicionar middleware de CORS no FastAPI para evitar bloqueios dependendo do browser:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Estrutura de arquivos

```
karaoke/
├── server/
│   ├── main.py               # FastAPI app, rotas HTTP e WebSocket
│   ├── stt_engine.py         # wrapper do faster-whisper
│   ├── score_engine.py       # lógica de pontuação por palavra com rapidfuzz
│   ├── song_manager.py       # carrega backing track, LRC e segments.json
│   ├── cert.pem              # certificado SSL autoassinado
│   ├── key.pem               # chave SSL
│   └── songs/
│       └── exemplo/
│           ├── vocal.mp3         # versão com vocal — usada APENAS pelo prepare_song.py
│           ├── backing_track.mp3 # versão instrumental — servida ao cliente durante o jogo
│           ├── lyrics.lrc
│           └── segments.json
├── tools/
│   └── prepare_song.py       # script offline que gera segments.json a partir do vocal.mp3+lrc
└── client/
    └── index.html            # cliente browser (single page)
```

---

## Duas versões de áudio por música

**`vocal.mp3`** — versão com vocal humano. Usada exclusivamente pelo `prepare_song.py` offline para o Whisper extrair o timing real de cada palavra como referência. Nunca é servida ao cliente.

**`backing_track.mp3`** — versão instrumental sem vocal. É o áudio que toca no browser durante o jogo. O Whisper nunca processa este arquivo.

Essa separação é necessária porque o LRC só tem timestamp por linha, não por palavra. O Whisper rodando sobre o `vocal.mp3` é a única fonte de timing de palavra preciso para popular o campo `expected_start` de cada palavra no `segments.json`.

---

## segments.json

Cada música tem um segments.json gerado pelo prepare_song.py. A fonte primária de segmentação são as **linhas do arquivo LRC** — cada linha do LRC define um segmento. O `detect_nonsilent` é usado apenas como ajuste fino opcional para refinar as bordas. Estrutura:

```json
[
  {
    "id": 1,
    "label": "Verso 1",
    "sing_start": 4.2,
    "sing_end": 22.8,
    "pause_start": 22.8,
    "pause_end": 25.4,
    "language": "en",
    "lyrics": "Is this the real life? Is this just fantasy?",
    "lyrics_timed": [
      { "word": "is",      "expected_start": 0.2 },
      { "word": "this",    "expected_start": 0.5 },
      { "word": "the",     "expected_start": 0.8 },
      { "word": "real",    "expected_start": 1.1 },
      { "word": "life",    "expected_start": 1.4 }
    ]
  }
]
```

O campo `expected_start` de cada palavra é relativo ao início do segmento (não ao início da música). É gerado pelo Whisper rodando sobre o trecho correspondente do `vocal.mp3`.

O campo `language` é passado diretamente ao faster-whisper na transcrição do jogador.

---

## tools/prepare_song.py

Roda offline uma vez por música. Recebe como argumentos:
- caminho do `vocal.mp3` (com vocal)
- caminho do `lyrics.lrc`
- caminho do `backing_track.mp3` (instrumental) — apenas para validar que existe, não é processado

Fluxo:

1. Parsear o arquivo LRC e extrair a lista de linhas com seus timestamps — cada linha do LRC define um segmento. O `sing_start` de cada segmento é o timestamp da linha no LRC. O `pause_start` é o timestamp da linha seguinte. Usar as linhas do LRC como fonte primária de segmentação, não o `detect_nonsilent`
2. Para cada segmento, extrair o trecho de áudio correspondente do `vocal.mp3` usando pydub e **converter para numpy array float32 antes de passar ao stt_engine**:
   - Converter o trecho para mono e resample para 16kHz ainda no pydub
   - Exportar para bytes raw PCM via `.raw_data`
   - Converter com `numpy.frombuffer(raw_data, dtype=numpy.int16).astype(numpy.float32) / 32768.0` para normalizar em [-1.0, 1.0]
   - Passar o numpy array resultante para `stt_engine.transcribe(audio_data, language)` com `word_timestamps=True`
3. Usar os `expected_start` retornados pelo Whisper para popular o `lyrics_timed` de cada segmento
4. Salvar o `segments.json` na pasta da música

O `stt_engine.py` é o módulo compartilhado entre `prepare_song.py` E `main.py` — ambos passam numpy arrays float32 16kHz mono.

---

## server/main.py

### Rota HTTP GET /
Serve o client/index.html

### Rota HTTP GET /songs
Retorna lista de músicas disponíveis em server/songs/

### Rota HTTP GET /songs/{song_id}/audio
Serve o `backing_track.mp3` da música. O `vocal.mp3` nunca é exposto por nenhuma rota.

### Rota WebSocket /ws/{song_id}

O WebSocket recebe dois tipos de mensagem do cliente:
- **Mensagem binária** — chunk de áudio PCM
- **Mensagem JSON** — evento de controle

#### Mensagens JSON do cliente para o servidor:

```json
{ "type": "client_info", "sample_rate": 48000 }
{ "type": "playback_time", "current_time": 12.53 }
```

O servidor usa o `current_time` recebido do cliente para decidir quando parar de acumular áudio de cada segmento — **nunca usa `time.time()` interno para sincronização**. Isso elimina o drift entre o relógio do servidor e o `<audio>` do browser, que podem dessincronizar por latência de rede, buffering e decode de MP3.

#### Fluxo principal:

1. Cliente conecta passando o song_id
2. Servidor aguarda mensagem JSON `client_info` com o `sample_rate` real do AudioContext do cliente e armazena para uso no resample
3. Servidor envia evento `segment_start` com id, label, sing_start, sing_end, lyrics e lyrics_timed completo do segmento atual
4. Cliente inicia o playback e começa a enviar:
   - Chunks de áudio PCM como ArrayBuffer binário
   - Eventos JSON `playback_time` a cada 500ms com o `audio.currentTime` atual
5. Servidor acumula os chunks binários em um bytearray
6. Servidor monitora os eventos `playback_time`. Quando `current_time >= sing_end` do segmento atual, para de acumular áudio
7. Servidor converte o bytearray acumulado:
   - `numpy.frombuffer(buffer, dtype=numpy.float32)` para obter o array bruto
   - Aplicar resample para 16kHz com `scipy.signal.resample` usando a proporção `16000 / sample_rate_recebido`
   - O resultado é um numpy float32 16kHz mono pronto para o Whisper
8. Passa o numpy array diretamente ao `stt_engine.transcribe()` — o faster-whisper aceita numpy arrays nativamente
9. Compara resultado da transcrição com lyrics_timed do segmento usando o score_engine
10. Envia evento `segment_result` com score do segmento, transcrição detectada e score total acumulado
11. Aguarda `current_time >= pause_end` (monitorando eventos `playback_time`) e avança para o próximo segmento
12. Repete até acabar os segmentos, envia evento `game_over` com score total

O servidor não envia eventos de highlight — isso é responsabilidade do cliente.

---

## server/stt_engine.py

- Carrega o modelo faster-whisper `medium` com `device="cuda"` e `compute_type="float16"` na inicialização (singleton, carrega uma vez). Trocar para `large-v3` se a GPU tiver 6GB+ de VRAM disponível
- Expõe função `transcribe(audio_data: numpy.ndarray, language: str) -> tuple[str, list[dict]]` que recebe numpy array float32 16kHz mono e retorna o texto transcrito e a lista de palavras com timestamps `[{ "word": str, "start": float }]`
- Este mesmo módulo é usado pelo `prepare_song.py` (para gerar referência de timing do vocal.mp3) e pelo `main.py` (para transcrever a voz do jogador em tempo de jogo) — a assinatura da função é idêntica nos dois casos

---

## server/score_engine.py

Lógica de pontuação por palavra:

1. Tokenize a letra esperada (lyrics_timed) e a transcrição em listas de palavras (lowercase, remove pontuação)
2. Para cada palavra esperada, percorra a lista de palavras transcritas **sequencialmente** e encontre a melhor correspondência usando `rapidfuzz.fuzz.ratio`. **Marcar a palavra transcrita como consumida** após o match para que não possa ser reutilizada — isso evita que palavras repetidas na letra (ex: "let it go let it go") sejam erroneamente matcheadas múltiplas vezes pela mesma palavra transcrita
3. Threshold de similaridade: >= 85 → 1 ponto, 70-84 → 0.5 ponto, < 70 → 0
4. Para cada palavra que passou no threshold, aplique penalidade de timing comparando `word.start` da transcrição com `expected_start` do segments.json. Usar janela temporal generosa para compensar imprecisão do Whisper em voz cantada:
   - diferença < 0.5s → sem penalidade
   - diferença 0.5–1.0s → perde 30% do ponto da palavra
   - diferença > 1.0s → perde 60% do ponto da palavra
5. Penalizar ausência: se a transcrição tem menos que 50% da quantidade de palavras esperadas, o segmento pontua zero independente do match
6. Score do segmento: soma dos pontos / total de palavras esperadas * 100 (escala 0-100)

---

## client/index.html

Single page, zero frameworks. Deve:

1. Ao carregar, buscar GET /songs e exibir lista de músicas disponíveis
2. Ao selecionar uma música, exibir um botão **"Iniciar"** — todo o setup de AudioContext, WebSocket e microfone deve acontecer dentro do handler de clique desse botão. O browser exige gesto explícito do usuário para:
   - Criar e resumir o AudioContext (`await audioContext.resume()`)
   - Chamar `audio.play()`
   - Obter permissão de microfone via getUserMedia

3. Ao clicar em "Iniciar":
   - Conectar no WebSocket `/ws/{song_id}`
   - Criar `AudioContext` sem forçar sampleRate — deixar o browser usar o rate nativo (tipicamente 48000Hz no Chrome). O servidor fará o resample
   - Obter o sample rate real: `const sampleRate = audioContext.sampleRate`
   - Chamar `await audioContext.resume()` para garantir que o contexto está ativo
   - Pedir permissão de microfone. Desligar todos os processamentos automáticos pois degradam qualidade de canto:
```javascript
await navigator.mediaDevices.getUserMedia({
  audio: {
    echoCancellation: false,
    noiseSuppression: false,
    autoGainControl: false,
    channelCount: 1
  }
});
```
   - Enviar handshake inicial ao servidor:
```javascript
ws.send(JSON.stringify({ type: "client_info", sample_rate: sampleRate }))
```

4. **CRÍTICO — AudioWorklet em arquivo único:** Como o cliente é um único arquivo HTML, não existe URL separada para o módulo do AudioWorklet. Implemente criando um Blob de string com o código JS do processador, gerando uma URL com `URL.createObjectURL(blob)` e passando para `audioContext.audioWorklet.addModule()`. O processador deve capturar apenas o canal 0 (mono) em Float32 e enviar chunks de **2048 samples** como ArrayBuffer binário via WebSocket

5. Criar um elemento `<audio>` e carregar GET /songs/{song_id}/audio para tocar o backing track. O `audio.play()` deve ser chamado dentro do handler de clique

6. Iniciar um loop que envia `playback_time` ao servidor a cada 500ms:
```javascript
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "playback_time", current_time: audio.currentTime }))
  }
}, 500)
```

7. Ao receber `segment_start`:
   - Ajustar `audio.currentTime` para `sing_start` do segmento se necessário
   - Renderizar as palavras do segmento na tela, todas em cinza
   - Iniciar um loop `requestAnimationFrame` que a cada frame compara `audio.currentTime - sing_start` com o `expected_start` de cada palavra em `lyrics_timed` e atualiza o visual:
     - Palavras com `expected_start` já ultrapassado → branco opaco ("já passou")
     - Palavra atual (maior `expected_start` ainda não ultrapassado) → amarelo brilhante, tamanho maior
     - Palavras futuras → cinza

8. Ao receber `segment_result`:
   - Parar o loop requestAnimationFrame
   - Exibir score do segmento, transcrição detectada ao lado da letra esperada, e score total acumulado

9. Ao receber `game_over`: exibir pontuação final e parar o `<audio>`

---

## Formato do áudio entre cliente e servidor

O cliente captura no sample rate nativo do browser (tipicamente 48000Hz) e envia chunks de 2048 samples como Float32LE binário via WebSocket.

O servidor:
1. Acumula os chunks como bytearray
2. Ao fim do segmento, converte com `numpy.frombuffer(buffer, dtype=numpy.float32)`
3. Aplica resample para 16kHz com `scipy.signal.resample` usando o sample rate informado no handshake `client_info`
4. Passa o numpy array float32 16kHz mono diretamente ao faster-whisper

Não há montagem de WAV — o faster-whisper aceita numpy arrays nativamente.

---

## Observações importantes

- O servidor deve rodar em `0.0.0.0` para ser acessível na rede local
- Para o MVP, uma música de cada vez, sem múltiplos jogadores simultâneos
- Não use APIs externas, tudo roda local
- O `vocal.mp3` nunca é servido ao cliente e nunca deve ser exposto por nenhuma rota HTTP
- O backing track é instrumental — o STT foca naturalmente na voz do jogador sem filtragem adicional
- Todo setup de áudio e WebSocket deve ocorrer dentro de um handler de clique explícito do usuário — nunca no carregamento da página
