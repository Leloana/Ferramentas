# Ecossistema Híbrido — Marco 1: Handoff com Apps-Equivalentes (Android → Windows)

Compartilhe (ou "arraste pro canto") algo no **Android** e ele continua no
**PC Windows** no *app equivalente*, no estado certo: YouTube no ponto do vídeo,
link no navegador, pasta no Explorer, arquivo no app padrão, texto no clipboard.
Estilo "Handoff" da Apple, sobre **SSH** na LAN (e **Tailscale** fora de casa).

> 📖 **Quer só usar?** Veja o **[Guia de Uso completo (passo a passo)](GUIA_DE_USO.md)** —
> do zero: servidor SSH no PC, Termux + chave no celular, instalar o agente,
> instalar e configurar o app, permissões, bolha de atalhos e personalização.

Visão completa, princípios e roadmap: ver [`PLANO.md`](PLANO.md). Este README
cobre o **Marco 1** (seção 5 do plano) e a **arquitetura/protocolo**.

## Como funciona

```
[Android]  --(compartilhar / handoff)-->  termux-url-opener / termux-handoff
     |  monta o DESCRITOR de handoff (JSON, PLANO.md seção 4)
     |  printf '<json>' | ssh pc-remoto "python agente.py --send"
     v
[PC Windows / sshd]  --(entrega o descritor, não abre nada)-->
     |
[Agente na SESSÃO DO USUÁRIO]  agente.py --daemon  (127.0.0.1:8765)
     |  resolve a Tabela de Apps-Equivalentes + fallback automático
     v
  navegador / Explorer / app padrão / clipboard  (VISÍVEL)
```

> **Lição da Sessão 0 × 1 (PLANO.md §3):** quem abre UI/apps tem que rodar na
> sessão interativa do usuário. Por isso o SSH **só entrega** o descritor ao
> daemon (`--send`); o **daemon** (iniciado pelo `start-agente.vbs` na pasta
> Startup) é quem abre as janelas — na tela visível, sem travar o perfil do Chrome.

## Descritor de handoff (protocolo)

Uma linha JSON por evento:

```jsonc
{
  "tipo": "midia" | "url" | "arquivo" | "pasta" | "texto" | "mapa" | "contato",
  "app_origem": "com.google.android.youtube",
  "dados": { "url": "...", "pos_segundos": 412, "caminho": "/DCIM/..." },
  "timestamp": 1730000000
}
```

| `tipo`    | `dados` esperados                  | Ação no Windows                                  |
|-----------|------------------------------------|-------------------------------------------------|
| `midia`   | `url`, `pos_segundos`              | YouTube → `youtu.be/<id>?t=<seg>`; senão abre URL |
| `url`     | `url`                              | Navegador padrão                                 |
| `pasta`   | `caminho` (Android)               | Explorer no caminho mapeado                      |
| `arquivo` | `caminho` (Android)               | App padrão do tipo                               |
| `texto`   | `conteudo`                        | Clipboard do PC                                  |
| `mapa`    | `lat`+`lng` / `query` / `url`     | Google Maps no navegador                         |
| `contato` | `vcard` (ou os próprios dados)    | Clipboard (sem equivalente curado ainda)         |

**Fallback automático** (sem linha curada): `http(s)` → navegador; `caminho` →
Explorer/app padrão. Linha não-JSON é tratada como **URL pura** (compat. com o
protótipo antigo).

## Arquivos

| Arquivo | Onde roda | Função |
|---|---|---|
| `agente.py` | PC (Windows, sessão do usuário) | Agente: resolve descritores → app equivalente |
| `config.json` | PC | Mapeamento de caminhos Android↔Windows (ver `config.example.json`) |
| `start-agente.vbs` | PC (pasta Startup) | Sobe o agente em daemon, oculto, no login |
| `setup-windows.ps1` | PC (admin) | Instala/config. OpenSSH Server + autoriza a chave do celular |
| `termux-url-opener` | Celular (`~/bin/`) | Share Sheet de link → descritor `url`/`midia` |
| `termux-handoff` | Celular (`~/bin/`) | Disparo genérico: `--pasta/--arquivo/--url/--texto/--mapa` |
| [`android/`](android/) | Celular (APK) | **App nativo** (Kotlin/Compose): gesto "arrastar pro canto" + share target |
| `ssh_config_termux` | Celular (`~/.ssh/config`) | Alias `pc-remoto` |
| `receiver.py` | PC | **Legado** (protótipo de URL). Absorvido por `agente.py`. |

> O `termux-*` é a **ponte interina**. O app Android nativo (APK) em
> [`android/`](android/) substitui esses scripts e leva o **estado completo**
> (timestamp do vídeo, caminho exato, seleção) via o gesto "arrastar pro canto".
> Usa o **mesmo transporte** (SSH → `agente.py --send`), então o lado PC não muda.

## Instalação

### 1. PC (Windows) — uma vez, como Administrador

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\mf827\Documents\Ferramentas\ecosistema\setup-windows.ps1" -PhonePubKey "ssh-ed25519 AAAA... termux-s24fe"
```

Depois:

```powershell
copy config.example.json config.json   # e ajuste o mapeamento de caminhos
# Sobe o agente agora e configura auto-start no login:
copy start-agente.vbs "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\"
wscript start-agente.vbs
```

### 2. Celular (Termux)

```bash
mkdir -p ~/bin
cp termux-url-opener termux-handoff ~/bin/ && chmod +x ~/bin/termux-url-opener ~/bin/termux-handoff
cat ssh_config_termux >> ~/.ssh/config
```

## Teste manual

```bash
# Link (qualquer app → Compartilhar → Termux), ou direto:
termux-handoff --url "https://example.com"
# YouTube com timestamp será suportado plenamente pelo app nativo; via share:
termux-url-opener "https://youtu.be/dQw4w9WgXcQ"
# Pasta → Explorer (precisa do mapeamento em config.json):
termux-handoff --pasta /storage/emulated/0/DCIM
# Texto → clipboard do PC:
echo "copia isto no PC" | termux-handoff --texto
```

Log do agente: `C:\Users\mf827\.handoff\agente.log`.

## Fora da Wi-Fi (Tailscale)

Instale o Tailscale no PC e no celular e troque o `HostName` em
`~/.ssh/config` (no celular) pelo IP `100.x.x.x` do PC.

## Próximos passos (PLANO.md)

- **App Android nativo (APK):** gesto "arrastar pro canto" + leitura do app em
  foco → leva o estado completo (timestamp, scroll, caminho).
- **PC → Android** (sentido inverso) e demais marcos: clipboard universal,
  AirDrop, pastas compartilhadas, espelhamento (ver §6 do plano).
