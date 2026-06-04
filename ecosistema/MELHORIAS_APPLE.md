# O que falta para ter o "jeito Apple" — propostas para avaliar

> Análise do estado atual (Android→PC já funciona: handoff de link/YouTube,
> clipboard, mapa, pasta, arquivo via SFTP, abrir apps do PC, bolha de atalhos)
> e do **gap** até a sensação de **Apple Continuity**. Cada proposta tem: *o que
> é*, *por que parece Apple*, *esforço* e *como fazer* tocando no código atual.
>
> Marque as que aprovar; a ordem no fim é minha recomendação.

---

## 1. O que "jeito Apple" realmente significa

Não é animação bonita — é um conjunto de **princípios de experiência**. O atual
acerta a base técnica, mas viola alguns destes:

| Princípio Apple | Hoje no Ecossistema | Gap |
|---|---|---|
| **Zero configuração** — você não digita IP, nem cola chave | Cola IP, porta, usuário e **chave PEM** na mão | 🔴 grande |
| **Proximidade/automático** — aparece sozinho quando faz sentido | Você **abre a bolha e toca** numa ferramenta | 🔴 grande |
| **Instantâneo** — sub-segundo, sem "carregando" | **SSH + boot do Python a cada evento** (~1–3 s) | 🔴 grande |
| **Bidirecional e simétrico** — vale dos dois lados igual | Quase tudo é **Android → PC** | 🟡 médio |
| **Continuar o estado** — documento/scroll/posição exatos | YouTube só pega `t=` se já estiver na URL | 🟡 médio |
| **Invisível e confiável** — retoma sozinho, enfileira offline | Se o PC dorme/cai, **falha** (toast de erro) | 🟡 médio |
| **Seguro sem fricção** — E2E por conta, sem o usuário pensar | `PromiscuousVerifier` (aceita qualquer host) + chave colada | 🔴 grande (segurança) |
| **Linguagem humana** — "Handoff", "AirDrop", não "ferramentas" | Bolha de emojis/"ferramentas" = vibe *power-user* | 🟢 pequeno |
| **Toque/som/movimento** — háptico no envio, "swoosh" | Toast de texto | 🟢 pequeno |

A regra-mestra da Apple: **"it just works" = o sistema decide e age; o usuário
não configura nem dispara.** É aí que está a maior distância.

---

## 2. As 3 mudanças que mais mudam a *sensação* (núcleo)

Se for fazer só três, são estas — elas transformam "script sobre SSH" em
"continuidade mágica".

### 🥇 A. Canal persistente de baixa latência (em vez de SSH por evento)
- **O que:** uma conexão **sempre aberta** entre app e agente (a sessão SSH já
  autenticada fica viva, ou um socket TLS próprio por dentro do túnel). Cada
  handoff vira só "escrever uma linha JSON" num canal já pronto.
- **Por que parece Apple:** mata a espera. Handoff da Apple é **instantâneo**
  porque o canal já existe. Hoje cada ação paga *connect + handshake + auth +
  `python` cold start* — é o que faz parecer "ferramenta", não "mágica".
- **Esforço:** médio-alto.
- **Como:** no `SshHandoffTransport`, em vez de abrir `SSHClient`/`startSession`
  a cada `send`, manter **um `Session.exec("python agente.py --serve")`** vivo e
  escrever várias linhas nele; o agente ganha um modo `--serve` que lê linha a
  linha do stdin (loop) em vez de 1 descritor e sai. Reconnect automático com
  backoff quando cair. (O `--send` atual vira fallback.)

### 🥈 B. Emparelhamento por QR (zero IP, zero chave colada)
- **O que:** no PC, o agente mostra um **QR** com `{host, porta, fingerprint da
  host key, token de pareamento}`. No app, **escaneia → pareado**. Nunca mais
  digitar IP nem colar PEM; a chave é **gerada no celular** e a pública é
  registrada no PC pelo token (uma vez).
- **Por que parece Apple:** é o "Sign in and you're done". Configuração some.
- **Esforço:** médio.
- **Como:** o `setup-windows.ps1`/agente expõe um comando `--pair` que gera token
  + mostra QR (lib `qrcode`); o app lê o QR (CameraX/MLKit), gera o par de chaves
  no Android Keystore, manda a pública pelo canal de pareamento, e o PC adiciona
  em `administrators_authorized_keys`. **Bônus de segurança:** já fixa o
  fingerprint → elimina o `PromiscuousVerifier`.

### 🥉 C. Handoff *proativo* (sem abrir a bolha)
- **O que:** quando você está num app "continuável" (vídeo, página, mapa) e
  **desbloqueia o PC** (ou vice-versa), aparece sozinho um aviso discreto
  *"Continuar 'Vídeo do YouTube' aqui?"* — um clique e pronto.
- **Por que parece Apple:** é **literalmente** o Handoff da Apple (o ícone no
  Dock/Multitarefa). O usuário não "envia"; ele **aceita uma sugestão**.
- **Esforço:** alto (é o mais ambicioso).
- **Como:** Accessibility já sabe o app/URL em foco no Android; publicar isso no
  canal como "atividade atual". O agente do PC, ao detectar **desbloqueio/foco**
  (ex.: `SessionSwitch`/`LockWorkStation` via API ou polling), mostra um toast
  acionável/balão na bandeja com a última atividade. Inverso: o app mostra uma
  notificação "Continuar do PC" quando o PC publica atividade.

---

## 3. Melhorias de simetria e robustez (o "just works")

### D. Universal Clipboard automático (bidirecional, sem botão)
- **O que:** copiou no celular → **cola no PC** direto (e vice-versa), sem tocar
  em "ferramenta de clipboard".
- **Por que Apple:** Universal Clipboard é invisível — o `Ctrl+V` simplesmente
  traz. Hoje existe a ferramenta `clipboard`, mas é **manual e só Android→PC**.
- **Esforço:** médio (Android 10+ limita ler clipboard em background — usar o
  próprio canal + um atalho/ं serviço de acessibilidade como gatilho de cópia).
- **Como:** ao copiar com o serviço ativo, empurra pelo canal; o agente seta o
  clipboard do Windows. PC→Android: agente observa o clipboard do Windows e
  publica; app escreve no clipboard do Android.

### E. Sentido PC → Android (de verdade)
- **O que:** mandar link/arquivo/clipboard **do PC para o celular**; abrir o app
  equivalente no Android.
- **Por que Apple:** Continuity é simétrico. Hoje é 90% Android→PC.
- **Esforço:** médio. **Como:** o agente vira também *emissor*; o app, com o canal
  persistente (A), age como *receptor* (abre URL/Intent, salva arquivo, etc.).

### F. Presença + fila offline + acordar o PC
- **O que:** o app **sabe** se o PC está acordado; se estiver dormindo, **acorda**
  (Wake-on-LAN) ou **enfileira** e dispara quando voltar. Nada de "deu erro".
- **Por que Apple:** Apple esconde indisponibilidade — enfileira e entrega depois.
- **Esforço:** médio. **Como:** heartbeat no canal (A) = presença; WoL por
  *magic packet* na LAN; fila local no app que faz flush no reconnect.

### G. Estado mais rico (continuar de verdade, não recomeçar)
- **O que:** posição do vídeo mesmo sem `t=` na URL, página do PDF, scroll, item
  selecionado.
- **Por que Apple:** "continuar no mesmo ponto" é a promessa central.
- **Esforço:** alto e por-app. **Como:** ler `MediaSession`/notificação de mídia
  para posição; Accessibility para scroll/seleção em apps-alvo (começar por
  YouTube/Chrome).

---

## 4. Polimento de "feel" (barato, alto impacto percebido)

Pequenos, mas é o que faz parecer **produto**, não protótipo:

- **H. Háptico + som + animação** no envio/sucesso (vibração curta, um "swoosh",
  um check animado). Hoje é um `Toast` de texto.
- **I. Linguagem humana:** trocar "Ferramentas" por experiências nomeadas —
  *Handoff*, *Área de transferência universal*, *Enviar arquivo (AirDrop)*. A
  bolha continua, mas com nomes que comunicam magia, não um "menu de scripts".
- **J. Bolha mais inteligente:** mostrar **só o que faz sentido agora** (se há
  URL em foco, destaca "Continuar no PC"; se há algo copiado, destaca clipboard).
  Contextual > grade fixa de emojis.
- **K. Feedback nos dois lados sincronizado:** o card de sucesso no celular e o
  toast no PC com o **mesmo nome da ação** ("YouTube continuado às 14:32").
- **L. Onboarding visual:** substituir o passo-a-passo do `GUIA_DE_USO.md` por um
  fluxo dentro do app (3 telas: parear (QR) → permissões → pronto).

---

## 5. Segurança no estilo Apple (segura **e** sem fricção)

A Apple é E2E mas o usuário nunca pensa nisso. Hoje há **duas dívidas**:

1. **`PromiscuousVerifier`** aceita qualquer host key → vulnerável a MITM na LAN.
   → Resolver junto do **QR pairing (B)**: o QR carrega o fingerprint; o app
   fixa (pinning). Fica seguro **sem** o usuário ver "known_hosts".
2. **Chave privada colada/manual** → gerar no **Android Keystore** (não-exportável)
   e registrar a pública via pareamento. O usuário nunca toca em PEM.

---

## 6. Recomendação de ordem (custo × impacto na sensação)

1. **A — canal persistente** → o maior salto de "feel" (instantâneo). Base p/ tudo.
2. **B — QR pairing** (+ pinning) → mata a maior fricção e a dívida de segurança.
3. **H/I/J — polimento + linguagem + bolha contextual** → barato, parece produto.
4. **D — clipboard universal automático** → função "invisível" clássica da Apple.
5. **E + F — PC→Android + presença/fila/WoL** → simetria e confiabilidade.
6. **C — handoff proativo** → o "santo graal"; fazer por último, depois do canal.
7. **G — estado rico** → contínuo, por-app, evolui sem prazo.

> Observação honesta: **A** e **B** sozinhos já mudam a percepção de "ferramenta
> de nerd" para "parece a Apple", mesmo sem o resto. Se o tempo for curto, são
> esses dois.

---

## 7. Interface no PC (bandeja + janelinha) — **sim, vale muito**

Hoje o lado PC é um daemon invisível que só dá toasts. A Apple sempre tem um
**lugar visível** onde a continuidade mora (Ajustes → AirDrop/Handoff, Central
de Controle, Finder). E tem um motivo prático forte: **o QR do pareamento (B)
precisa ser mostrado em algum lugar no PC** — uma janelinha é o lar natural.

Por que vale:
- É onde o **QR de pareamento** aparece (destrava a proposta B sem CLI).
- Dá **presença visível**: qual celular está conectado, online/offline, IP,
  última atividade, bateria (se o app publicar).
- Vira o **painel de saúde**: sshd ligado? porta 22 aberta? Tailscale? log? — em
  vez de o usuário caçar isso no PowerShell (hoje espalhado em `CONEXAO_SSH.md`).
- Transforma "script + bandeja" em **produto** — alinhado com I/L da seção 4.

### O que a janela mostra (4 abas simples)
1. **Conectar** — QR grande + "Escaneie no app do celular". Mostra o
   fingerprint/host embutido. (É a cara do onboarding Apple.)
2. **Dispositivos** — card por celular pareado: nome, IP, **bolinha
   online/offline**, última atividade ("YouTube às 14:32"), botão *Desparear*.
3. **Ações rápidas** — poucos botões, sentido **PC → celular** (casa com E):
   enviar link/arquivo/clipboard pro celular; abrir a pasta **Ecossistema**
   (onde caem os arquivos via SFTP); toggle do **clipboard universal** (D).
4. **Ajuda / diagnóstico** — "Testar conexão", status do sshd/porta/Tailscale,
   abrir o log, reabrir o setup. Botão de "copiar relatório" pra quando travar.

### Bandeja (tray)
Ícone fixo com menu: *Abrir painel* · *Status: ● conectado a S24 FE* · *Pasta
Ecossistema* · *Iniciar no login* · *Sair*. Clique no ícone abre a janela. O
ícone reflete presença (cor/badge) — feedback ambiente, estilo Apple.

### Stack — 3 opções para você escolher (impacto no instalador importa)

| Opção | Visual | Dependência / tamanho | Quando escolher |
|---|---|---|---|
| **pywebview** (HTML/CSS no webview do SO) | 🟢 moderno, fácil deixar bonito | leve-médio (usa o Edge WebView2 já no Win11) | **recomendado** — melhor "feel" por pouco custo |
| **tkinter** (vem com o Python) | 🟡 datado, mas funcional | **zero** dependência extra | se quiser o instalador mínimo |
| **PySide6/Qt** | 🟢 nativo caprichado | 🔴 pesado (infla muito o .exe) | só se virar app "de verdade" no futuro |

Tray em qualquer caso: **pystray + Pillow**; QR com **qrcode[pil]** (já entra
junto da proposta B).

**Recomendação:** **pywebview + pystray**. O daemon já roda na **sessão do
usuário** (lição da Sessão 0×1), então é o host perfeito pra abrir a janela; e o
canal persistente (A) alimenta presença/última-atividade da aba *Dispositivos*
de graça. Esforço: **médio** — e entrega B, parte de E/F e o polimento L de uma vez.

> Dependência saudável: a janela do PC só fica "viva" de verdade junto da
> proposta **A** (canal persistente) e **B** (QR). Faz sentido construí-la
> **junto** desses dois, não antes.

---

## 8. Fora de escopo agora (mas no radar do PLANO.md)

Notificações espelhadas, chamadas/SMS no PC, espelhar tela (scrcpy), webcam,
segunda tela (Sidecar), auto-unlock. São marcos seguintes — não atacam a
*sensação* do handoff básico, então ficam depois dos itens 1–6.
