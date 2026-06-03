# Ecossistema Híbrido — Handoff de Links (Android → Windows)

Compartilhe um link de **qualquer app do Android** e ele abre automaticamente
no navegador padrão do **PC Windows**. Estilo "Handoff" da Apple, feito com
**SSH** sobre a rede local (e, opcionalmente, **Tailscale** para uso fora de casa).

> **Refinamento:** o `PLANO.md` original assumia um PC **Ubuntu**
> (`xdg-open`, `systemd`, FIFO). Esta versão foi reescrita para **Windows**:
> `receiver.py` abre o navegador via `webbrowser`/`os.startfile`, e o disparo
> usa `ssh ... python receiver.py --once` (sem daemon nem systemd).

## Topologia

```
[Android/Termux]  --(compartilhar link)-->  termux-url-opener
        |  ssh pc-remoto "python receiver.py --once <URL>"
        v
[PC Windows / sshd]  -->  receiver.py  -->  navegador padrão abre o link
```

- Celular: Samsung S24 FE, Termux, IP `192.168.15.3`.
- PC: Windows 11, usuário `mf827`, IP `192.168.15.6`, porta SSH `22`.

## Arquivos

| Arquivo | Onde roda | Função |
|---|---|---|
| `receiver.py` | PC (Windows) | Abre a URL no navegador (`--once` ou `--daemon`) |
| `setup-windows.ps1` | PC (Windows, **admin**) | Instala/config. OpenSSH Server + autoriza a chave do celular |
| `termux-url-opener` | Celular (`~/bin/`) | Recebe a URL compartilhada e envia via SSH |
| `ssh_config_termux` | Celular (`~/.ssh/config`) | Alias `pc-remoto` |

## Instalação

### 1. PC (Windows) — uma vez, como Administrador

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\mf827\Documents\Ferramentas\ecosistema\setup-windows.ps1" -PhonePubKey "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIATeDDk1k0pPWsZkrFqPofxtekhdAAzxZNL2YBKN8fg6 termux-s24fe"
```

Isso instala o OpenSSH Server, habilita o serviço `sshd` (auto-start), abre a
porta 22 no firewall e autoriza a chave pública do celular.

### 2. Celular (Termux) — já configurado por este projeto

- Chave SSH gerada em `~/.ssh/id_ed25519`.
- `~/.ssh/config` com o alias `pc-remoto`.
- `~/bin/termux-url-opener` instalado e executável.
- (Opcional) Notificações: instale o app **Termux:API** + `pkg install termux-api`.

## Teste

```bash
# No Termux:
ssh pc-remoto "python \"C:\\Users\\mf827\\Documents\\Ferramentas\\ecosistema\\receiver.py\" --once \"https://example.com\""
# Ou compartilhe um link de qualquer app -> escolha "Termux" -> URL abre no PC.
```

Log do receiver: `C:\Users\mf827\.handoff\daemon.log`.

## Fora da Wi-Fi (Tailscale, opcional)

Instale o Tailscale no PC e no celular, e troque o `HostName` em
`~/.ssh/config` (no celular) pelo IP `100.x.x.x` do PC.

## Modo daemon (opcional)

Em vez de spawnar Python a cada link, é possível manter um listener:

```powershell
python receiver.py --daemon   # escuta em 127.0.0.1:8765
```
(O modo `--once` via SSH é o padrão recomendado — mais simples e robusto.)
