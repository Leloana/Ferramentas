# Como conectar no celular via SSH (Termux)

Guia para acessar o celular **Samsung S24 FE** (Android + Termux) a partir
deste PC Windows, usando SSH com autenticação por chave (sem senha).

---

## Dados da conexão

| Item        | Valor                          |
|-------------|--------------------------------|
| Host (IP)   | `192.168.15.3`                 |
| Porta       | `8022` (padrão do Termux)      |
| Usuário     | `u0_a550`                      |
| Autenticação| Chave SSH (ed25519) — sem senha |
| Pasta de dev| `~/storage/shared/code`        |

> O IP `192.168.15.3` vale enquanto o celular estiver na **mesma rede Wi-Fi**.
> Se mudar de rede ou reiniciar, confira o IP de novo com `ifconfig wlan0` no Termux.

---

## Comando rápido (a partir do PC)

```powershell
ssh -p 8022 u0_a550@192.168.15.3
```

Entrar e já cair na pasta de desenvolvimento:

```powershell
ssh -p 8022 u0_a550@192.168.15.3 "cd ~/storage/shared/code && bash"
```

Rodar um comando único sem abrir sessão interativa:

```powershell
ssh -p 8022 -o BatchMode=yes u0_a550@192.168.15.3 "ls -la ~/storage/shared/code"
```

---

## Pré-requisitos no celular (Termux)

1. **Instalar o servidor SSH** (uma vez):
   ```bash
   pkg update && pkg upgrade
   pkg install openssh
   ```

2. **Iniciar o servidor SSH** (toda vez que reabrir o Termux):
   ```bash
   sshd
   ```
   Não mostra nada se der certo. A porta é a **8022** (apps sem root não
   podem usar a porta 22).

3. **Manter o Termux acordado** (evita o Android matar o `sshd`):
   ```bash
   pkg install termux-api
   termux-wake-lock
   ```
   E desative a otimização de bateria do Termux nas configurações do Android.

4. **Acesso à storage compartilhada** (uma vez), para enxergar `~/storage`:
   ```bash
   termux-setup-storage
   ```

---

## Configuração da chave SSH (já feita — só para referência)

A autenticação é por chave, não por senha. A chave pública do PC já foi
adicionada ao celular. Caso precise refazer (PC novo ou chave perdida):

1. **No PC** — gerar a chave (se não existir) e ver a pública:
   ```powershell
   ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\id_ed25519" -N '""'
   Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
   ```

2. **No celular (Termux)** — autorizar a chave pública:
   ```bash
   mkdir -p ~/.ssh && chmod 700 ~/.ssh
   echo 'COLE_A_CHAVE_PUBLICA_AQUI' >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```

---

## Descobrir o IP do celular (se mudar)

No Termux:
```bash
ifconfig wlan0      # procure "inet 192.168.x.x"
# ou
ip addr
```

---

## Solução de problemas

| Problema                              | Causa provável / solução                                   |
|---------------------------------------|------------------------------------------------------------|
| `Connection refused`                  | `sshd` não está rodando → rode `sshd` no Termux            |
| `Connection timed out`                | IP errado ou redes diferentes → confira `ifconfig wlan0`  |
| Conexão cai sozinha                   | Android matou o Termux → use `termux-wake-lock`           |
| Pede senha mesmo com chave            | Permissões erradas → `chmod 700 ~/.ssh` + `600 authorized_keys` |
| `Permission denied` em `~/storage`    | Rode `termux-setup-storage` e dê a permissão no Android   |

---

## Observações sobre a pasta de desenvolvimento

A pasta `~/storage/shared/code` fica na **storage compartilhada do Android**
(sistema de arquivos `media_rw`). Limitações conhecidas:

- Em algumas configs **não dá para usar `chmod +x`** (criar executáveis).
- O `git` pode reclamar de permissões de arquivos.
- Editar e rodar scripts (`python arquivo.py`) funciona normalmente.

Para trabalhos que exijam permissões completas (git, builds, venv), prefira
uma pasta dentro do próprio Termux, como `~/code`, em vez da storage compartilhada.

---

## Testar pela internet (fora do Wi-Fi local)

Pelo 4G/5G o IP muda e fica atrás de NAT da operadora. Para acessar de fora,
use uma VPN de rede como o **Tailscale**:
```bash
pkg install tailscale
tailscaled &      # inicia o daemon
tailscale up      # autentica
```
Depois conecte usando o IP do Tailscale (faixa `100.x.x.x`) na porta `8022`.
