# Plano de testes — Ecossistema Híbrido

> Checklist para validar o fluxo ponta a ponta. Está dividido em:
> 1. **Testes de DEV** — rodam **agora, em qualquer máquina** (Linux/macOS/WSL),
>    sem o PC de casa, sem SSH e sem o celular. Provam a lógica.
> 2. **Marco 1** — handoff Android→PC (já provado em 2026-06-03).
> 3. **Fase A (hardware)** — canal persistente real.
> 4. **Fase B (hardware)** — emparelhamento por QR + pinning.
> 5. **Regressão / robustez** e **riscos a confirmar**.
>
> Legenda: `[x]` validado · `[ ]` pendente · `[~]` parcial.
> Marque conforme for testando e anote o resultado na linha.

---

## 1. Testes de DEV (sem hardware) — rodam agora

Provam o **núcleo** do canal persistente (A) e do pareamento (B) com 2 processos
locais. Nenhum exige Windows, SSH ou o celular. `pareamento.py` em SO não-Windows
grava em `~/.ssh/authorized_keys` (em vez do `administrators_authorized_keys`).

### DEV-A — Canal persistente (proposta A)

- [x] **DEV-A1. Sintaxe:** `python3 -c "import ast; ast.parse(open('agente.py').read())"`
      e idem `pareamento.py`. → OK (dev 2026-06-04).
- [x] **DEV-A2. Relay `--serve` ↔ daemon (stdio bidirecional):**
      ```bash
      HANDOFF_PORT=8799 python3 agente.py --daemon >/dev/null 2>&1 &
      sleep 0.6
      printf '%s\n' '{"_ctrl":"hello","device":"s24fe","name":"S24 FE"}' '{"_ctrl":"ping"}' \
        | HANDOFF_PORT=8799 BROWSER=true python3 agente.py --serve
      ```
      Esperado na stdout do `--serve`: `{"_ctrl": "ack", "ok": true}` e
      `{"_ctrl": "pong"}`. → OK (dev 2026-06-04).
- [x] **DEV-A3. Controle + presença + push + descritor (in-process):**
      hello→ack+online, ping→pong, activity→atualiza, descritor url→resolve,
      `push_para_dispositivo`→chega na stdout do serve, desconexão→offline.
      → OK (dev 2026-06-04, via `socketpair`).
- [ ] **DEV-A4. Compat `--send` intacto:** com o daemon de pé,
      `echo '{"tipo":"url","app_origem":"t","dados":{"url":"https://example.com"},"timestamp":0}' | HANDOFF_PORT=8799 python3 agente.py --send`
      → daemon resolve (log) e `--send` retorna 0.
- [ ] **DEV-A5. Linha não-JSON = URL pura (compat antiga):**
      `echo 'https://example.com' | HANDOFF_PORT=8799 python3 agente.py --send`
      → tratado como URL.

### DEV-B — Emparelhamento por QR (proposta B)

- [x] **DEV-B1. Fingerprint = `ssh-keygen -lf`:** gerar uma `.pub` e conferir que
      `pareamento.host_key_fingerprint()` dá o mesmo `SHA256:...`.
      → OK (dev 2026-06-04: bate com `ssh-keygen -lf` e com o cálculo manual).
- [x] **DEV-B2. Handshake token-gated:** subir `servir_pareamento` e simular o
      celular. Token errado → `{"ok":false,"erro":"token invalido"}`; token certo
      → `{"ok":true,"user":...}` e a chave é gravada no `authorized_keys`.
      → OK (dev 2026-06-04).
- [x] **DEV-B3. Protocolo idêntico ao `PairingManager.kt`:** payload
      `{token,pubkey,name,device}` aceito; `name`/`device` retornados no resultado.
      → OK (dev 2026-06-04).
- [x] **DEV-B4. Formato da chave OpenSSH:** o PEM que o `KeyManager` embrulha tem
      `-----BEGIN/END OPENSSH PRIVATE KEY-----`; a linha pública é
      `ssh-ed25519 <b64> ecossistema`. → conferido contra `ssh-keygen` (dev 2026-06-04).
- [ ] **DEV-B5. `--pair-info` (para a UI):** `python3 agente.py --pair-info`
      imprime JSON `{v,host,...,fp,token,pair_port}` válido (1 linha).
- [ ] **DEV-B6. `--pair` (CLI):** `python3 agente.py --pair` mostra host/fp/token
      e (se `pip install qrcode`) o QR em ASCII; fica aguardando o pareamento.

> **Atalho:** os snippets exatos de DEV-A2/A3/B1/B2/B3 estão no `README.md`
> (seções "Canal persistente" e "Emparelhamento por QR").

---

## 2. Marco 1 — handoff Android→PC (já provado)

> **PROVADO ponta a ponta em 2026-06-03** (PC→ssh→celular→ssh→sshd→`agente.py --send`
> →daemon→janela visível). Resumo dos critérios:

- [x] YouTube com timestamp → `youtu.be/<id>?t=<seg>` abriu na tela.
- [x] URL/aba → navegador abriu na tela.
- [x] Pasta → Explorer abriu no caminho mapeado.
- [x] Texto → clipboard do Windows.
- [x] Arquivo via SFTP → pasta `Ecossistema` + abre no app padrão.
- [x] App picker (abrir programa do PC).
- [ ] **A10 (pendente):** confirmar **visualmente** o toast do Windows.

Pré-requisitos do PC (uma vez, como admin): `setup-windows.ps1 -PhonePubKey ...`
(OpenSSH Server + firewall 22 + chave autorizada). Daemon no login via
`start-agente.vbs` na pasta Startup.

---

## 3. Fase A no hardware — canal persistente real

Prova que o app mantém **uma** sessão SSH viva e que cada handoff é instantâneo.

### Pré-requisitos
- [ ] **A-pre1.** PC com daemon de pé na sessão do usuário (`start-agente.vbs`).
- [ ] **A-pre2.** App buildado com as mudanças (ver Fase D do histórico):
      `./gradlew assembleDebug` → instalar o APK.
- [ ] **A-pre3.** App configurado (por QR — Fase B — ou conexão manual legada).

### Testes
- [ ] **A1. Canal sobe:** ligue a "Bolha de atalhos" (Foreground Service). No
      `agente.log` do PC deve aparecer **`Canal persistente ON: <device>`**.
- [ ] **A2. Presença no daemon:** o dispositivo fica registrado como `online`
      (visível depois pela UI do PC; por ora confirmável no log/estado).
- [ ] **A3. Latência (o ponto-chave):** dispare um handoff de link **com o canal
      já aberto**. Deve abrir **quase instantâneo** (sem o ~1–3 s de antes).
      Compare com o fallback (A6).
- [ ] **A4. Heartbeat:** deixe o app ocioso > 20 s; o canal continua `online`
      (pings periódicos no log). Sem desconexões espúrias.
- [ ] **A5. Reconnect + backoff:** desligue o Wi-Fi do celular por ~30 s e religue
      → o canal volta sozinho (log: OFF e depois ON). Backoff cresce até religar.
- [ ] **A6. Fallback `--send`:** **pare** a bolha (canal cai) e dispare um handoff
      pela share sheet → deve **funcionar mesmo assim** (abre via `--send`).
- [ ] **A7. Fila offline:** com o canal caindo no meio, o evento enfileirado deve
      ser entregue ao reconectar (não some).
- [ ] **A8. Sessão 0×1 preservada:** confirme que as janelas abrem na **tela
      visível** (o `--serve` roda no sshd/sessão 0, mas só repassa ao daemon).

---

## 4. Fase B no hardware — emparelhamento por QR + pinning

Prova o "parear e pronto" e a remoção da dívida de segurança.

### Pré-requisitos
- [ ] **B-pre1.** sshd no PC já rodando (host key ed25519 existente em
      `C:\ProgramData\ssh\ssh_host_ed25519_key.pub`).
- [ ] **B-pre2.** `qrcode` instalado no PC se for usar o QR pelo CLI
      (`pip install qrcode[pil]`); ou usar a UI do PC quando existir.

### Testes
- [ ] **B1. Mostrar o QR:** `python agente.py --pair` no PC → mostra host, porta,
      user, fingerprint, token e o QR (ASCII no CLI).
- [ ] **B2. Escanear no app:** tocar **"Parear com QR"** → câmera abre → ler o QR.
- [ ] **B3. Permissão de câmera:** na 1ª vez o Android pede CAMERA → conceder.
- [ ] **B4. Geração da chave:** o app gera o par ed25519 (1ª vez) sem pedir nada
      ao usuário (nada de colar PEM).
- [ ] **B5. Elevação (UAC):** no PC aparece **um** prompt de UAC para autorizar a
      chave → aceitar. A pública entra no `administrators_authorized_keys`.
- [ ] **B6. Sucesso:** o app mostra "Pareado com <host>!" e o card de status vira
      **Conectado** (sem digitar IP nem chave).
- [ ] **B7. Pinning ativo:** depois de pareado, um handoff conecta normalmente
      (fingerprint confere). Para provar o pinning, troque a host key do PC
      (`ssh-keygen -A` forçado/renomear) → a conexão deve **falhar** (host key não
      confere) em vez de aceitar cegamente.
- [ ] **B8. Token de uso único / janela:** após parear (ou após ~3 min), o canal
      de pareamento fecha; um 2º pareamento exige novo `--pair` (novo token).
- [ ] **B9. Token inválido:** apontar o app para um QR com token adulterado →
      pareamento recusado ("token invalido").
- [ ] **B10. Convivência com legado:** uma config antiga (chave colada, sem
      fingerprint) continua funcionando (cai no verificador promíscuo de fallback).

---

## 5. Regressão / robustez

- [ ] **R1. `--send` puro** (sem canal): handoff via share sheet ainda abre no PC.
- [ ] **R2. `--list-apps`** continua retornando o JSON de apps do PC.
- [ ] **R3. SFTP** (enviar arquivo) abre na pasta `Ecossistema` e no app padrão.
- [ ] **R4. App morto pela Samsung** → Foreground Service volta e o canal religa.
- [ ] **R5. PC suspenso/desligado** → handoff não trava o app (erro tratado);
      ao voltar, o canal reconecta.
- [ ] **R6. Tailscale (fora da Wi-Fi):** parear/usar com host `100.x` (o QR já traz
      `tshost` quando o Tailscale está ligado).
- [ ] **R7. Boot do celular:** após reiniciar, o serviço/overlay voltam
      (RECEIVE_BOOT_COMPLETED).

---

## 6. Riscos conhecidos a confirmar no hardware

- [ ] **RISCO-1 (alto): interop BouncyCastle ↔ sshj.** A chave gerada pelo
      `KeyManager` (via `OpenSSHPrivateKeyUtil`) precisa ser lida pelo
      `ssh.loadKeys(...)` do sshj na hora de autenticar. Formato conferido em dev,
      mas o byte-a-byte só se prova autenticando de verdade (B6/A1).
      **Plano B se falhar:** gerar a chave via `net.i2p.crypto:eddsa` (já é dep) ou
      cair temporariamente para a chave colada (config legada segue válida).
- [ ] **RISCO-2: EncryptedSharedPreferences** inicializa em todos os aparelhos
      alvo (minSdk 26). Se falhar, `KeyManager` cai para vazio e usa a chave colada.
- [ ] **RISCO-3: toast do Windows** (Marco 1 A10) ainda não confirmado visualmente.

---

## 7. Critérios de "A + B prontos"

**A pronto:**
- [ ] Canal sobe e fica `online` com heartbeat estável (A1, A2, A4).
- [ ] Handoff perceptivelmente **instantâneo** com o canal aberto (A3).
- [ ] Reconnect automático e fallback `--send` funcionando (A5, A6).

**B pronto:**
- [ ] Parear com QR sem digitar IP nem colar chave (B1–B6).
- [ ] Pinning ativo (host key trocada → conexão recusada) (B7).
- [ ] Legado segue funcionando (B10).
