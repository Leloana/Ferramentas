# Arquitetura do cliente (para IA)

Este documento descreve a organização do código em `client/`. Antes era um único `index.html` de 3132 linhas; foi modularizado preservando 100% do comportamento. Leia isto antes de editar.

## Layout

```
client/
├── index.html              # Shell HTML: <link> CSS, todo o markup, <template> de song-card, <script type="module" src="/js/main.js">
├── styles/
│   └── main.css            # Todo o CSS, incluindo classes de estado novas (ver "Convenção CSS" abaixo)
└── js/
    ├── main.js             # Entry point. Decide bootstrap por myRole, faz wiring de listeners globais.
    ├── state.js            # Estado mutável compartilhado entre módulos (objeto exportado).
    ├── dom.js              # Cache central de getElementById via getters.
    ├── config.js           # Constantes de URL/role/room (read-only).
    ├── api.js              # NÃO existe — chamadas fetch ficaram inline nos módulos que as usam.
    ├── toast.js            # showToast.
    ├── sync.js             # syncOffset, volume do backing, startTimeSync, updateSyncDisplay.
    ├── mic-stream.js       # getMicrophoneStream (fallbacks de constraints).
    ├── mic-status.js       # updateMicStatusPanel, checkInitialMicPermission.
    ├── ws-display.js       # connectDisplayWebSocket (papel display).
    ├── ws-mic.js           # connectMobileMicrophoneWebSocket (papel mic).
    ├── mobile-mic-view.js  # UI do celular: ativação do mic, VU meter, mute, exit.
    ├── selection-view.js   # Lista de músicas, busca, render, seleção, abrir editor LRC.
    ├── game-view.js        # Loop do karaokê: startKaraoke, handleServerMessage, render lyrics, highlight, game over.
    ├── modals.js           # add-song (tabs + advanced toggle + submit), pairing (QR), lrc-editor.
    └── worklets/
        └── audio-processor.js   # AudioWorklet (carregado via audioWorklet.addModule).
```

## Servidor (FastAPI)

`server/main.py` serve:
- `/` → `client/index.html`
- `/styles/*` → `client/styles/` (StaticFiles mount)
- `/js/*` → `client/js/` (StaticFiles mount, recursivo, alcança `js/worklets/`)

Não há build step. Os módulos JS são servidos como estão e carregados pelo browser via `<script type="module">`.

## Regra crítica: estado compartilhado

ES modules exportam **bindings imutáveis** para primitivos. Para que vários módulos compartilhem estado mutável (ex.: `state.ws`, `state.isSingingActive`), usamos um objeto exportado:

```js
// state.js
export const state = { ws: null, isSingingActive: false, /* ... */ };

// consumidor
import { state } from './state.js';
state.ws = new WebSocket(...);          // OK — muta propriedade do objeto
state.isSingingActive = data.active;    // OK
```

**NÃO** faça `export let ws = null` esperando reatribuir de fora — isso não funciona como em globals do navegador.

Campos atuais em `state.js`:

| Campo | Quem escreve | Para que serve |
|---|---|---|
| `selectedSongId` | selection-view | id da música escolhida |
| `allSongs` | selection-view | cache para busca |
| `ws` | ws-display, game-view, main | WebSocket do papel display |
| `mobileWs` | ws-mic | WebSocket do papel mic |
| `transcriptionActiveTimer` | game-view | timeout para retornar HUD "Ouvi" |
| `audioContext` | game-view | AudioContext do canto local |
| `currentSegments` | (reservado) | — |
| `currentSegmentData` | game-view | segmento atual recebido do servidor |
| `lastSegmentLyricsTimed` | game-view | usado para verde/vermelho da transcrição |
| `animationId` | game-view | id do rAF do highlight loop |
| `syncOffset` | sync, game-view (reset) | ajuste manual de sincronia em segundos |
| `isFirstSegment` | game-view | controle do primeiro carrossel sem fade |
| `totalPauseDuration` | game-view | duração de pausa instrumental |
| `pauseStartTarget` | game-view | tempo-alvo do fim da pausa |
| `isMobileMicrophoneConnected` | game-view (via WS), main (reset) | celular pareado? |
| `localStreamForced` | mic-status, main (botão PC) | usuário forçou mic do PC? |
| `micSourceMode` | main | informativo: 'pc' |
| `isSingingActive` | ws-mic, game-view (via WS) | servidor liberou o canto? |
| `isOutroActive` | game-view (via WS, reset) | tocando outro instrumental |
| `outroStartPlayerTime` | game-view | timestamp do início do outro |
| `outroTotalDuration` | game-view | duração total do outro |
| `micMuted` | mobile-mic-view | celular mutado pelo usuário |
| `activeUploadTab` | modals | 'youtube' ou 'local' |

## Convenção CSS

Estilos inline em `style="..."` no markup **foram preservados** quando são valores estáticos (gradients, paddings, layouts fixos). Não tente movê-los todos para o CSS — é volume desnecessário.

**Apenas estados discretos manipulados por JS** viraram classes. Quando precisar mudar visual baseado em estado, use `classList.add/remove/toggle`, não `.style.x = ...`:

| Classe | Onde | Significado |
|---|---|---|
| `.mic-badge--idle` / `--pc` / `--mobile` / `--both` | header status | Estado do mic |
| `.btn-mobile-activate--active` / `--muted` | tela celular | Botão grande de mic |
| `.btn-mobile-mute--muted` | tela celular | Botão de mute |
| `.tab-btn--active` / `--inactive` | modal add-song | Aba youtube vs local |
| `.advanced-toggle--open` | modal add-song | Painel avançado expandido |
| `.song-card__edit-btn` / `__delete-btn` | lista de músicas | Inclui `:hover` em CSS |

Mantenha esse padrão. Se um novo estado precisa ser representado, adicione classe — não atribua `.style.x`.

## Padrões de import

- Módulos só importam o que usam. Não há `import *`.
- Ciclo conhecido: `ws-display.js` ↔ `game-view.js` (handleServerMessage). Funciona porque ambas funções são chamadas em runtime, não no top-level. Não introduza novos ciclos sem o mesmo cuidado.
- `dom.js` exporta `dom` (com getters) e `$id` (alias de `document.getElementById`). Prefira `dom.algumElemento`; use `$id('...')` só para IDs raramente acessados.

## Quirks do comportamento original que foram preservados

1. **Reconnect do WS display**: só reconecta automaticamente se a tela de seleção estiver visível ([ws-display.js](js/ws-display.js)). Quando inicia o canto, fecha o WS antigo e abre um novo com `song_id` na URL ([game-view.js](js/game-view.js) em `startKaraoke`).
2. **Handshake**: cliente envia `{type:"client_info", sample_rate}` logo após `onopen` em ambos os papéis. Não remover.
3. **Constraints do mic**: lista de 3 fallbacks na ordem (estrito → ideals → `audio: true`). iOS/Safari rejeita o primeiro às vezes.
4. **AudioWorklet com buffer de 4096 amostras**: definido em `worklets/audio-processor.js`. Carregado via `audioWorklet.addModule('/js/worklets/audio-processor.js')` em `mobile-mic-view.js` e `game-view.js`.
5. **localStorage**: chaves `karaoke_room_id`, `karaoke_backing_volume`, `karaoke_onboarding_seen`. NÃO renomeie.
6. **`role=mic` URL param**: faz o bootstrap pular toda a UI do display e mostrar só a `#mobile-mic-area`. Roteado em `main.js` via `myRole`.
7. **Modo solo (celular como TV)**: detectado em `config.js` (`isSoloMobileMode`). Quando true, oculta botões "Conectar PC/Celular" e assume `localStreamForced = true`.

## Como adicionar uma feature

- **Novo estado compartilhado**: adicione campo em `state.js` e documente na tabela acima.
- **Novo elemento DOM acessado de múltiplos lugares**: adicione getter em `dom.js`.
- **Nova chamada de API**: faça inline no módulo da view que a usa (não há `api.js` ainda; se ficar repetitivo, extraia).
- **Novo estado visual**: adicione classe em `styles/main.css`, toggle via `classList`.
- **Novo modal**: adicione markup em `index.html` (junto dos outros modais) e wiring em `modals.js`.
- **Novo evento WS**: trate em `handleServerMessage` ([game-view.js](js/game-view.js)) para display, ou no `onmessage` de [ws-mic.js](js/ws-mic.js) para o celular.

## O que NÃO fazer

- Não introduza bundler, npm, TypeScript ou framework. O projeto é vanilla intencional.
- Não exporte `let` primitivos esperando reatribuição cross-module. Use `state.js`.
- Não duplique o AudioWorklet inline — use o arquivo externo.
- Não troque `classList` por `.style.x =` para representar estados.
- Não renomeie IDs sem auditar `dom.js`, `main.css` e todos os módulos que usam.
- Não adicione comentários explicativos onde o código já é claro. Preserve o estilo enxuto.

## Histórico

Refatoração de `index.html` monolítico (3132 linhas) feita em uma única passada. Servidor recebeu apenas dois `app.mount` adicionais para servir `/styles` e `/js`; nenhuma rota existente foi alterada.
