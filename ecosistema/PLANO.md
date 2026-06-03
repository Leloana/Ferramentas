# Ecossistema Híbrido Android ↔ Windows

> Objetivo: replicar — e superar — o **Apple Continuity** entre um Android
> (Samsung S24 FE) e um PC Windows, com fluidez parecida com a da Apple.
> Onde o Windows não tem o app equivalente do Android (ou vice-versa), o
> ecossistema resolve o **equivalente** automaticamente.

---

## 1. Visão

Os dois aparelhos se comportam como **um só ambiente**. O usuário não pensa
"mandar arquivo por SSH"; ele faz um gesto natural e a coisa simplesmente
acontece no outro dispositivo:

- Vendo um vídeo no YouTube no celular → **arrasta para um canto** → o vídeo
  continua no PC, **no mesmo ponto** (e o inverso também).
- Mexendo numa pasta no gerenciador de arquivos do Android → **arrasta para o
  PC** → o **Explorer abre na pasta exata**.
- Copiou um texto/imagem num → **cola no outro** (clipboard universal).
- "Joga" um arquivo de um para o outro como num **AirDrop**.
- Bibliotecas de pastas **compartilhadas dinamicamente** entre os dois.

Princípio central: **mapa de apps-equivalentes**. Cada ação carrega *o que* o
usuário estava fazendo (app + dado + estado), e o destino escolhe o melhor app
local para continuar — de forma **hardcoded** (curada) ou **automática** (por
tipo de conteúdo / esquema de URL).

---

## 2. Princípios de design

1. **Gesto > menu.** A interação primária é gestual (arrastar, jogar), não
   navegar menus. Por isso o lado Android é um **app nativo (APK)**.
2. **Continuar o estado, não só o link.** Handoff leva contexto (timestamp do
   vídeo, scroll, caminho, seleção), não apenas a URL.
3. **Bidirecional.** Toda função vale Android→PC e PC→Android sempre que fizer
   sentido.
4. **Privado e local-first.** Comunicação direta entre os aparelhos (LAN ou
   mesh Tailscale), criptografada, sem nuvem de terceiros.
5. **Degradação graciosa.** Se não houver equivalente perfeito, cai para o mais
   próximo (ex.: app → site no navegador) em vez de falhar.

---

## 3. Arquitetura

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│        APP ANDROID          │  canal  │        AGENTE WINDOWS         │
│  (Kotlin/Compose, APK)      │◄──────► │  (bandeja, sessão do usuário) │
│  - gestos / drag&drop       │  seguro │  - executa ações no Windows   │
│  - share targets nativos    │  (TLS)  │  - abre apps/Explorer/browser │
│  - overlay "arrastar canto" │         │  - clipboard / arquivos       │
│  - serviço em foreground    │         └──────────────┬───────────────┘
└──────────────┬──────────────┘                        │
               │      Rede: LAN (mesma Wi-Fi) ou Tailscale (100.x mesh)
               └───────────────────────────────────────┘
                 Descoberta: mDNS/NSD na LAN + Tailscale fora dela
                 Transporte: canal de controle JSON sobre TLS;
                             arquivos grandes via stream dedicado.
```

### Componentes

- **App Android (APK nativo):** Kotlin + Jetpack Compose. Foreground Service
  para manter o canal vivo; share targets para "Compartilhar → Ecossistema";
  overlay/handle para o gesto "arrastar pro canto"; provider de arquivos.
- **Agente Windows:** processo na **sessão interativa do usuário** (ícone na
  bandeja). É ele quem abre janelas/Explorer/navegador de forma **visível**.
- **Canal de controle:** mensagens JSON (tipo + payload) sobre conexão TLS
  persistente. Reusa o backbone **SSH/Tailscale** que já configuramos para
  bootstrap/segurança, mas a troca de eventos é por esse canal próprio.
- **Emparelhamento:** troca de chaves uma vez (como o "pairing" do KDE Connect),
  com confirmação no PC. Dispositivos confiáveis ficam salvos.

### ⚠️ Restrição de design aprendida (Windows: sessão 0 × sessão 1)

Processos lançados por **serviço** (ex.: `sshd`, que roda como SYSTEM) ficam na
**Sessão 0**, que **não tem área de trabalho visível**. Abrir o navegador dali
cria uma janela invisível e ainda **trava o lock de perfil do Chrome**, fazendo
lançamentos seguintes (até manuais) serem "engolidos" pelo processo fantasma.

**Regra:** quem mostra UI / abre apps tem que ser o **Agente Windows rodando na
sessão interativa do usuário**. O canal vindo de fora (celular) só **entrega o
evento** ao agente; nunca abre app diretamente a partir de um contexto de
serviço/SSH. (Foi exatamente o bug do protótipo de handoff de URL.)

---

## 4. Conceito central: Tabela de Apps-Equivalentes

Cada handoff carrega um **descritor** independente de plataforma:

```jsonc
{
  "tipo": "midia" | "url" | "arquivo" | "pasta" | "texto" | "mapa" | "contato",
  "app_origem": "com.google.android.youtube",
  "dados": { "url": "...", "pos_segundos": 412, "caminho": "/DCIM/..." },
  "timestamp": 1730000000
}
```

O destino resolve o equivalente por uma tabela curada + regras automáticas:

| Conteúdo / App Android         | Equivalente no Windows                         | Estado levado          |
|--------------------------------|------------------------------------------------|------------------------|
| YouTube (vídeo)                | YouTube no navegador padrão (`&t=` no ponto)   | timestamp do vídeo     |
| Gerenciador de arquivos (pasta)| **Explorer** na pasta mapeada                  | caminho exato          |
| Chrome/aba                     | Navegador padrão (mesma URL)                   | URL, scroll (futuro)   |
| Google Maps (local)            | Maps no navegador / app de mapas               | coordenadas/place      |
| Spotify / YT Music             | App/desktop equivalente no mesmo ponto         | faixa + posição        |
| Galeria (foto)                 | Visualizador de Fotos / pasta no Explorer      | arquivo                |
| Documento (PDF/Office)         | App padrão do tipo no Windows                  | arquivo + página       |
| Texto selecionado / nota       | Bloco de notas / clipboard                     | conteúdo               |

Regras automáticas (fallback quando não há linha curada):
- `http(s)://` → navegador padrão.
- arquivo/pasta → resolve caminho Android↔Windows e abre no app padrão/Explorer.
- tipo MIME → app padrão do Windows para aquele MIME.

> O mapeamento de **caminhos** Android↔Windows é configurável (ex.:
> `/storage/emulated/0/` ↔ uma pasta sincronizada/SSHFS no PC).

---

## 5. Marco 1 (foco atual): Handoff de mídia/links com apps-equivalentes

**Entregável:** arrastar um vídeo/aba/pasta no Android para um canto → continua
no PC no app equivalente, no estado certo. Inicialmente Android→PC; depois
PC→Android.

Escopo do Marco 1:
1. **Gesto no app Android:** "arrastar para o canto" dispara o handoff do app em
   foco (começando por YouTube, navegador e gerenciador de arquivos).
2. **Descritor de handoff** (seção 4) montado no Android.
3. **Agente Windows** recebe na sessão interativa e:
   - YouTube → abre `https://youtu.be/<id>?t=<seg>` no navegador padrão.
   - URL/aba → abre a URL.
   - Pasta → abre o **Explorer** no caminho mapeado.
4. **Tabela de equivalentes** mínima (curada) + fallback automático por esquema.
5. **Feedback:** confirmação visual nos dois lados (toast/bandeja).

Critério de pronto: os 3 casos (YouTube com timestamp, URL, pasta→Explorer)
funcionando de forma **visível e confiável**, com o agente na sessão do usuário.

---

## 6. Catálogo completo de funcionalidades (Continuity e além)

Marcos seguintes, priorizáveis depois do Marco 1:

| # | Funcionalidade Apple        | Nossa versão Android ↔ Windows                              |
|---|-----------------------------|------------------------------------------------------------|
| A | Handoff                     | **Marco 1** — handoff de mídia/links/pasta com equivalentes|
| B | Universal Clipboard         | Clipboard universal bidirecional (texto + imagem)          |
| C | AirDrop                     | Enviar arquivos/fotos "jogando" entre os aparelhos         |
| D | iCloud Drive / Bibliotecas  | **Pastas compartilhadas dinâmicas** (SSHFS/rclone/sync)    |
| E | iPhone Mirroring            | Espelhar e **controlar o Android no PC** (scrcpy)          |
| F | Notificações no Mac         | **Notificações do Android espelhadas** no Windows          |
| G | Chamadas/SMS no Mac         | Atender chamada / ler e responder SMS pelo PC              |
| H | Continuity Camera           | Usar o celular como **webcam** do PC                        |
| I | AirPlay                     | Enviar mídia/áudio do PC para o celular (e vice-versa)      |
| J | Sidecar                     | Celular como **segunda tela** / painel de controle do PC   |
| K | Auto Unlock                 | **Destravar o PC** quando o celular confiável está perto    |
| L | Instant Hotspot             | Ligar o roteamento do celular pelo PC com um clique         |
| M | Find My                     | **Localizar dispositivos** (tocar alarme, status, IP)      |
| N | Continuity Markup/Sketch    | Anotar no celular um arquivo aberto no PC                   |

Extras "e muito mais" (além da Apple):
- **Sincronizar abas/sessão de navegador** entre os dois.
- **Enviar comandos/macros** do celular para o PC (atalho remoto).
- **Transferência de sessão de terminal** / executar scripts remotos.
- **Sincronizar entrada** (usar o teclado do PC para digitar no celular).
- **Modo apresentação:** celular vira controle remoto de slides/mídia no PC.

---

## 7. Stack técnica proposta

**App Android (APK):**
- Kotlin + Jetpack Compose; Foreground Service persistente.
- Descoberta: Network Service Discovery (mDNS) na LAN; Tailscale fora dela.
- Integrações: Share Sheet (share targets), `ACTION_VIEW`/intents para ler o app
  em foco, `Storage Access Framework`/FileProvider para arquivos, overlay
  (`SYSTEM_ALERT_WINDOW`) para o gesto "arrastar pro canto".
- Acessibilidade/`UsageStats` (com permissão) para inferir o app/estado atual.

**Agente Windows:**
- Processo na **sessão interativa** (bandeja). Linguagem: Python (rápido de
  evoluir, já temos base) ou C#/.NET (melhor integração de UI/bandeja) — decidir.
- Abre navegador/Explorer/apps **visivelmente** (lição da seção 3).
- Auto-start no login (já temos o mecanismo via pasta Startup).

**Rede e segurança:**
- Tailscale para mesh fora de casa; LAN direta dentro de casa.
- Canal TLS com emparelhamento por chave + confirmação; lista de dispositivos
  confiáveis. Backbone SSH atual serve para bootstrap/setup.

---

## 8. Roadmap em fases

- **Fase 0 — Fundação (parcialmente feita):** OpenSSH no PC, chaves do celular,
  Tailscale-ready, mecanismo de auto-start, protótipo de handoff de URL
  (e a lição da sessão 0/1).
- **Fase 1 — Marco 1:** App Android mínimo + Agente Windows + handoff de
  mídia/links/pasta com tabela de equivalentes (seção 5).
- **Fase 2 — Produtividade diária:** Clipboard universal (B) + AirDrop (C).
- **Fase 3 — Arquivos:** Bibliotecas/pastas compartilhadas dinâmicas (D).
- **Fase 4 — Tela:** Espelhar/controlar o Android no PC (E) + notificações (F).
- **Fase 5 — Avançado:** câmera (H), auto-unlock (K), chamadas/SMS (G) e os
  extras.

---

## 9. Estado atual (o que já existe nesta pasta)

- `receiver.py` — recebe URLs e abre no navegador (modos `--once`/`--send`/
  `--daemon`). Será absorvido/evoluído pelo **Agente Windows**.
- `setup-windows.ps1` — instala/configura OpenSSH Server, firewall e chave.
- `start-daemon.vbs` — sobe o daemon oculto na sessão do usuário (auto-start).
- `termux-url-opener`, `ssh_config_termux` — protótipo do lado celular (Termux),
  a ser substituído pelo **app Android nativo**.
- `README.md` — guia do protótipo atual.

> O protótipo Termux validou o transporte (celular→PC por SSH/Tailscale) e
> expôs a restrição de sessão do Windows. O ecossistema "de verdade" troca o
> Termux pelo app nativo e o daemon pelo Agente Windows com UI.

---

## 10. Decisões em aberto / riscos

- **Linguagem do Agente Windows:** Python (continuidade) × C#/.NET (UI nativa).
- **Construir do zero × reaproveitar KDE Connect** para funções já maduras
  (clipboard, arquivos, notificações, controle): decidido **app nativo do zero**
  para o Marco 1; reavaliar reuso nas fases 2–4 para acelerar.
- **Gesto "arrastar pro canto":** exige overlay + leitura do app em foco
  (permissões sensíveis de acessibilidade/overlay no Android).
- **Mapeamento de caminhos** Android↔Windows para pastas (config inicial).
- **Bateria/persistência** do serviço Android (otimizações do fabricante).
- **Sentido do handoff de vídeo:** confirmar se "arrastar pro canto" leva o
  vídeo do celular **para o PC** (assumido) e/ou o contrário.
