# Guia de Uso — Ecossistema Híbrido (Android → PC)

Guia **completo e do zero** para colocar o ecossistema funcionando: configurar o
PC (servidor SSH + agente), preparar o celular (Termux + chave SSH), instalar e
configurar o app Android, e usar a **bolha de atalhos** para mandar coisas do
celular pro PC (link da tela, texto copiado, abrir um app, etc.).

> **O que ele faz:** você toca um atalho no celular e a ação acontece **na tela
> do seu PC** — abre um link no navegador, um vídeo do YouTube no ponto certo, a
> pasta no Explorer, cola um texto, ou abre um programa do PC. Tudo por **SSH**
> na sua rede local (e via **Tailscale** fora de casa).

---

## Índice

1. [Como funciona (visão rápida)](#1-como-funciona-visão-rápida)
2. [Pré-requisitos](#2-pré-requisitos)
3. [Passo 1 — Celular: Termux + chave SSH](#3-passo-1--celular-termux--chave-ssh)
4. [Passo 2 — PC: servidor SSH (OpenSSH)](#4-passo-2--pc-servidor-ssh-openssh)
5. [Passo 3 — PC: instalar o agente](#5-passo-3--pc-instalar-o-agente)
6. [Passo 4 — PC: mapear pastas (config.json)](#6-passo-4--pc-mapear-pastas-configjson)
7. [Passo 5 — Celular: instalar o app (APK)](#7-passo-5--celular-instalar-o-app-apk)
8. [Passo 6 — Celular: configurar a conexão no app](#8-passo-6--celular-configurar-a-conexão-no-app)
9. [Passo 7 — Celular: conceder as permissões](#9-passo-7--celular-conceder-as-permissões)
10. [Passo 8 — Usar a bolha de atalhos](#10-passo-8--usar-a-bolha-de-atalhos)
11. [Passo 9 — Personalizar ferramentas](#11-passo-9--personalizar-ferramentas)
12. [Fora de casa (Tailscale)](#12-fora-de-casa-tailscale)
13. [Alternativa sem o app: ponte Termux](#13-alternativa-sem-o-app-ponte-termux)
14. [Solução de problemas](#14-solução-de-problemas)
15. [Onde ficam os arquivos e logs](#15-onde-ficam-os-arquivos-e-logs)

---

## 1. Como funciona (visão rápida)

```
[Celular / App]  toca um atalho na bolha (ou compartilha um link)
     |  monta um DESCRITOR (JSON) e abre uma conexão SSH com o PC
     v
[PC / servidor SSH (sshd)]  recebe e ENTREGA o descritor ao agente
     |   (não abre nada aqui — essa sessão é "invisível")
     v
[PC / agente em daemon, na SUA sessão]  (127.0.0.1:8765)
     |   resolve o que fazer e abre na TELA VISÍVEL
     v
  navegador / Explorer / app / clipboard
```

Duas peças no PC:
- **Servidor SSH (OpenSSH)** — porta de entrada do celular.
- **Agente** (`ecossistema-agente.exe` ou `agente.py`) — roda como **daemon
  invisível na sua sessão** e é quem **abre as janelas na tela**. O SSH só
  *entrega* o pedido ao agente (assim a janela abre visível, e não num "fundo"
  invisível).

> Não tem interface no PC — é um motor silencioso. Toda a UI fica no celular.
> O único retorno visual no PC são as notificações (toast) e as ações em si.

---

## 2. Pré-requisitos

**No PC (Windows 10/11):**
- Conta de usuário (de preferência a que você usa no dia a dia).
- Acesso de **Administrador** (só uma vez, para instalar o servidor SSH).
- Rede: PC e celular na **mesma Wi-Fi/LAN** (ou Tailscale, ver §12).

**No celular (Android):**
- **Termux** (de preferência do [F-Droid](https://f-droid.org/packages/com.termux/),
  não da Play Store — a versão da Play está desatualizada).
- O app **Ecossistema** (APK — ver Passo 5).

> Você **não** precisa de Python no PC se usar o **instalador** (Passo 3, opção A).
> O agente vai empacotado como `.exe`.

---

## 3. Passo 1 — Celular: Termux + chave SSH

A autenticação é por **chave** (sem senha). Geramos a chave **no celular**; a
parte pública dela é autorizada no PC no Passo 2.

No **Termux**:

```bash
# 1. Atualiza e instala o cliente SSH
pkg update && pkg upgrade -y
pkg install -y openssh

# 2. Gera o par de chaves (aperte Enter em tudo — SEM senha/passphrase)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N ""

# 3. Mostra a chave PÚBLICA — copie a linha inteira (começa com "ssh-ed25519 ...")
cat ~/.ssh/id_ed25519.pub
```

Guarde essa linha pública — você vai colá-la no Passo 2.

> A chave **privada** (`~/.ssh/id_ed25519`) fica no celular e será colada no app
> (Passo 6). Como não tem senha, o app autentica sozinho.

---

## 4. Passo 2 — PC: servidor SSH (OpenSSH)

Abra o **PowerShell como Administrador** (Win+X → "Terminal (Admin)") e rode o
script de setup, **colando a chave pública do celular** (do Passo 1):

```powershell
cd "C:\Users\<SEU_USUARIO>\Documents\Ferramentas\ecosistema"
powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1 -PhonePubKey "ssh-ed25519 AAAA...COLE_AQUI... termux"
```

O script (idempotente — pode rodar de novo sem medo):
- Instala e habilita o **OpenSSH Server** (serviço `sshd`, auto-start).
- Abre a **porta 22** no firewall (todos os perfis).
- **Autoriza a chave pública** do celular (em `administrators_authorized_keys`).
- Imprime no fim o **usuário** e o **IP LAN** do PC — anote os dois.

> **Por que admin:** se sua conta Windows é administradora, o sshd lê a chave de
> um arquivo protegido (`administrators_authorized_keys`), e só admin grava lá.

Descubra (ou confirme) o **IP do PC** a qualquer momento:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like "192.168.*" } | Select IPAddress, InterfaceAlias
```

---

## 5. Passo 3 — PC: instalar o agente

Escolha **uma** opção.

### Opção A — Instalador (recomendado, sem Python)

1. Pegue/gere o instalador `Ecossistema-Setup-<versão>.exe`
   (em `installer/dist/`; para gerar do zero, ver [installer/build.ps1](installer/build.ps1)).
2. Execute o instalador (instala **por-usuário**, sem pedir admin). Ele:
   - copia o agente para `%LOCALAPPDATA%\Programs\Ecossistema`,
   - liga o **auto-start no login** (registro `HKCU\...\Run`),
   - cria o `config.json` em `%APPDATA%\Ecossistema` (ver Passo 4),
   - oferece **"Iniciar o agente agora"** no fim — deixe marcado.

O caminho do agente (você vai usar no app, Passo 6) fica:

```
C:\Users\<SEU_USUARIO>\AppData\Local\Programs\Ecossistema\ecossistema-agente.exe
```

### Opção B — Modo dev (com Python)

Precisa de **Python 3.12+** no PATH.

```powershell
cd "C:\Users\<SEU_USUARIO>\Documents\Ferramentas\ecosistema"
# Sobe o agente agora e configura auto-start no login:
copy start-agente.vbs "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\"
wscript start-agente.vbs
```

O caminho do agente para o app é o próprio script:

```
C:\Users\<SEU_USUARIO>\Documents\Ferramentas\ecosistema\agente.py
```

> O app sabe lidar com os dois: se o caminho termina em `.exe`, ele roda direto;
> senão, usa `python "<script>.py>"`.

**Confira se o agente está no ar** (em qualquer opção):

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen
```

---

## 6. Passo 4 — PC: mapear pastas (config.json)

O `config.json` diz como traduzir os caminhos do **Android** para os caminhos do
**Windows** (para o atalho de abrir pasta funcionar).

- **Instalador (Opção A):** edite `%APPDATA%\Ecossistema\config.json`.
- **Dev (Opção B):** copie e edite na pasta do projeto:
  ```powershell
  copy config.example.json config.json
  ```

Exemplo:

```jsonc
{
  "mapeamento_caminhos": [
    { "android": "/storage/emulated/0/",          "windows": "C:\\Users\\voce\\Documents" },
    { "android": "/storage/emulated/0/DCIM/",      "windows": "C:\\Users\\voce\\Pictures" },
    { "android": "/storage/emulated/0/Download/",  "windows": "C:\\Users\\voce\\Downloads" }
  ]
}
```

> Use sempre o prefixo Android mais específico primeiro. Se nada casar, o agente
> usa o caminho original (degradação graciosa). Reinicie o agente depois de
> editar (ou faça logoff/login) para ele recarregar a config.

---

## 7. Passo 5 — Celular: instalar o app (APK)

1. **Obtenha o APK.** Gere com o Android Studio / Gradle a partir de
   [`android/`](android/) (`./gradlew assembleDebug` → `app/build/outputs/apk/debug/app-debug.apk`),
   ou use um APK já gerado.
2. **Transfira para o celular** (cabo, Drive, ou — se já tiver SSH no celular —
   `scp`). Coloque em `Download`, por exemplo.
3. **Instale:** abra **Meus Arquivos → Download → o APK → Instalar**.
   - Se pedir, autorize **"instalar apps desconhecidos"** para o gerenciador de arquivos.
   - Se o **Play Protect** avisar (é normal em APK fora da loja): toque em
     **"Mais detalhes" → "Instalar mesmo assim"**.

---

## 8. Passo 6 — Celular: configurar a conexão no app

Abra o app **Ecossistema** → aba **Início** → seção **"Conexão com o PC"**
(toque para expandir) e preencha:

| Campo | Valor |
|---|---|
| **Host** | IP LAN do PC (ex.: `192.168.15.6`) — do Passo 2 |
| **Usuário do Windows** | seu usuário do PC (ex.: `mf827`) |
| **Porta SSH** | `22` |
| **Caminho do agente** | o caminho do Passo 3 (`...\ecossistema-agente.exe` **ou** `...\agente.py`) |
| **Chave privada (PEM)** | conteúdo de `~/.ssh/id_ed25519` (veja abaixo) |

Para a chave privada, no **Termux**:

```bash
cat ~/.ssh/id_ed25519
```

Selecione **tudo** (do `-----BEGIN OPENSSH PRIVATE KEY-----` ao
`-----END OPENSSH PRIVATE KEY-----`, inclusive), copie e cole no campo.

Toque em **Salvar conexão** (aparece um toast "Conexão salva"). No topo, o card
de status deve ficar **verde "Conectado"** com `usuário@host`. Toque no card para
reverificar a qualquer momento.

> 🔴 Vermelho "Sem conexão" = PC desligado, agente parado, SSH não configurado,
> IP errado, ou chave não autorizada. Veja a [§14](#14-solução-de-problemas).

---

## 9. Passo 7 — Celular: conceder as permissões

Ainda na aba **Início**, role até **Permissões**. Legenda: **❗ = obrigatória**,
**✅ concedida**, **❌ falta**.

| Permissão | Para quê | Obrigatória? |
|---|---|---|
| **Sobreposição (overlay)** | a **bolha** aparecer sobre os apps | **Sim** ❗ |
| **Acessibilidade** | a ferramenta **"Link da tela"** ler a URL aberta | **Sim** ❗ (p/ esse atalho) |
| **Notificações** | mostrar a notificação fixa do serviço | recomendada |
| **Acesso de uso** | inferir o app em foco | opcional |
| **Ignorar otimização de bateria** | evitar o sistema matar o serviço | opcional |

Toque em **Abrir** em cada uma e conceda na tela do sistema. Ao voltar pro app,
o ✅/❌ se atualiza sozinho.

---

## 10. Passo 8 — Usar a bolha de atalhos

Na aba **Início**, ligue o **switch "Bolha de atalhos"**. Surge uma **bolha azul
flutuante** sobre todos os apps.

- **Toque na bolha** → abre o **leque de ferramentas** (ícones).
- **Toque num ícone** → executa o atalho (manda pro PC). Um **toast** confirma
  ("Enviado ao PC…") ou explica a falha.
- **Toque na bolha de novo** → fecha o leque (tocar fora **não** fecha).
- **Arraste a bolha** → reposiciona; ao soltar, **gruda na borda**.
- **Após reiniciar o celular**, a bolha **volta sozinha**.

Você também pode **compartilhar** um link de qualquer app → **Ecossistema** →
abre no PC (share target), sem usar a bolha.

---

## 11. Passo 9 — Personalizar ferramentas

Na aba **Ferramentas**, cada ferramenta tem **ícone + nome + descrição + como
funciona + um toggle**. O que você **ligar** aparece no leque da bolha (lá só o
ícone). Mudanças valem **na hora**, sem reiniciar a bolha.

Ferramentas prontas:

| Ícone | Nome | O que faz |
|---|---|---|
| 🔗 | Link da tela | manda a URL do navegador aberto pro PC (precisa da Acessibilidade) |
| 📋 | Texto copiado | cola no PC o texto copiado no celular |
| 🗺️ | Endereço copiado no Mapa | abre o endereço/coordenada copiado no Google Maps do PC |
| 📁 | Abrir Downloads no PC | abre a pasta Downloads no Explorer |
| 🧪 | Testar conexão | abre example.com no PC (para validar) |

### Ferramenta personalizada — abrir um app do PC

Na aba **Ferramentas**, toque em **"➕ Adicionar app do PC"**. O app **busca a
lista de programas do seu PC** (atalhos do Menu Iniciar) via SSH, mostra um
seletor com filtro, e você escolhe. A nova ferramenta entra no leque (ícone = a
inicial do nome) e, ao tocar, **abre aquele app no PC**. Dá pra ligar/desligar
ou apagar (🗑) quando quiser.

> ⚠️ O **Texto copiado** depende do clipboard do Android, que no Android 10+
> pode vir vazio quando o app não está em foco — nesse caso o app avisa por toast.

---

## 12. Fora de casa (Tailscale)

Fora da sua Wi-Fi, o IP `192.168.x` não vale. Instale o **Tailscale** no PC e no
celular (mesma conta), e no app troque o **Host** pelo IP `100.x.x.x` do PC
(o Tailscale mostra). O resto é igual. A porta continua `22`.

---

## 13. Alternativa sem o app: ponte Termux

Dá pra usar **sem o APK**, direto pelo Termux (útil para testar o transporte).

```bash
# Instale os scripts no celular:
mkdir -p ~/bin
cp termux-url-opener termux-handoff ~/bin/ && chmod +x ~/bin/termux-*
cat ssh_config_termux >> ~/.ssh/config   # cria o alias "pc-remoto" (ajuste o IP)
```

Use:

```bash
termux-handoff --url   "https://example.com"     # link → navegador do PC
termux-handoff --pasta /storage/emulated/0/DCIM  # pasta → Explorer
echo "texto" | termux-handoff --texto            # texto → clipboard do PC
termux-handoff --mapa  "Av Paulista, Sao Paulo"  # endereço → Google Maps
# Ou: qualquer app → Compartilhar → Termux → termux-url-opener
```

> Edite o `PC_AGENTE` dentro dos scripts se o caminho do agente no PC for outro.
> O `ssh_config_termux` usa o alias `pc-remoto` — ajuste `HostName`/`User` nele.

---

## 14. Solução de problemas

| Sintoma | Causa provável / solução |
|---|---|
| Card **vermelho "Sem conexão"** | PC desligado; agente parado (cheque a porta 8765); IP errado; redes diferentes; chave não autorizada. |
| `Permission denied` no SSH | A chave pública do celular não foi autorizada no PC → rode o `setup-windows.ps1` (admin) com a `-PhonePubKey` certa. |
| `Connection refused` / `timed out` | `sshd` não está rodando no PC; firewall; IP errado; PC e celular em redes diferentes. |
| A **bolha não aparece** | Falta a permissão **Sobreposição (overlay)** — o app avisa por toast. Conceda e ligue o switch de novo. |
| **"Link da tela" diz "nenhuma URL em foco"** | Ative a **Acessibilidade** e tenha um **navegador com a página aberta** em foco. |
| **"Texto copiado" vem vazio** | Limite do Android 10+ (clipboard em segundo plano). Copie e tente de novo com o app/recente em foco. |
| Abre, mas **numa tela invisível** | O agente precisa rodar na **sua sessão** (auto-start via instalador/HKCU\Run ou `start-agente.vbs`). Não rode o agente "à mão" por SSH. |
| Play Protect **bloqueia o APK** | "Mais detalhes" → "Instalar mesmo assim" (ou desligue temporariamente o Play Protect). |
| Dois agentes brigando pela porta 8765 | Você tem o instalador **e** o `start-agente.vbs` na Startup. Deixe **só um**. |

Diagnóstico rápido (no Termux) — testa o SSH puro até o PC:

```bash
ssh -i ~/.ssh/id_ed25519 <USUARIO>@<IP_DO_PC> "echo ok"
```

---

## 15. Onde ficam os arquivos e logs

| Item | Caminho |
|---|---|
| **Log do agente** | `C:\Users\<voce>\.handoff\agente.log` (uma linha por evento) |
| **config.json** (instalador) | `%APPDATA%\Ecossistema\config.json` |
| **config.json** (dev) | pasta do projeto (`ecosistema\config.json`) |
| **Agente** (instalador) | `%LOCALAPPDATA%\Programs\Ecossistema\ecossistema-agente.exe` |
| **Auto-start** (instalador) | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\EcossistemaAgente` |
| **Auto-start** (dev) | `start-agente.vbs` na pasta Startup do Windows |
| **Chaves SSH do celular** | `~/.ssh/id_ed25519` (privada) e `.pub` (pública) no Termux |

---

Detalhes de arquitetura, protocolo do descritor e roadmap: ver
[`README.md`](README.md) e [`PLANO.md`](PLANO.md).
