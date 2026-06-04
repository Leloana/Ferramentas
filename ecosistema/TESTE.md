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
- [x] **DEV-A4. Compat `--send` intacto:** com o daemon de pé,
      `echo '{"tipo":"url","app_origem":"t","dados":{"url":"https://example.com"},"timestamp":0}' | HANDOFF_PORT=8799 python3 agente.py --send`
      → daemon resolve (log) e `--send` retorna 0. → OK (2026-06-04, Windows).
- [x] **DEV-A5. Linha não-JSON = URL pura (compat antiga):**
      `echo 'https://example.com' | HANDOFF_PORT=8799 python3 agente.py --send`
      → tratado como URL. → OK (2026-06-04, Windows).

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
- [x] **DEV-B5. `--pair-info` (para a UI):** `python3 agente.py --pair-info`
      imprime JSON `{v,host,...,fp,token,pair_port}` válido (1 linha).
      → OK (2026-06-04). **Bug achado+corrigido:** `fp` vinha `None` no Windows
        porque a ACL de `ProgramData\ssh` nega leitura da `.pub` ao não-admin.
        Fix: fallback via `ssh-keyscan` (pega a host key pela rede). O `fp` agora
        bate com `ssh-keygen -lf`.
- [x] **DEV-B6. `--pair` (CLI):** `python3 agente.py --pair` mostra host/fp/token
      e (se `pip install qrcode`) o QR em ASCII; fica aguardando o pareamento.
      → OK (2026-06-04). **Bug achado+corrigido:** `print(ascii_qr)` quebrava com
        `UnicodeEncodeError` (console cp1252 × blocos do QR). Fix: stdout/err em
        UTF-8 no início do `main()` (também deixa `--list-apps` robusto a acentos).

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
- [x] **A1. Canal sobe:** ligue a "Bolha de atalhos" (Foreground Service). No
      `agente.log` do PC deve aparecer **`Canal persistente ON: <device>`**.
      → OK (hw 2026-06-04): `Canal persistente ON: samsung-SM-S721B`. **Bug
        achado+corrigido:** o canal caía a cada **3 s** (ON/OFF perfeito). Causa:
        `create_connection(timeout=3)` deixava o timeout do connect grudado no
        socket; a leitura do daemon no `--serve` estourava `socket.timeout` aos 3 s
        ociosos (1º heartbeat só aos 20 s). Fix `sock.settimeout(None)` (commit
        do canal). Pós-fix o canal passou a viver ~20 s (limite do heartbeat) —
        validando A4/estabilidade em andamento.
- [x] **A2. Presença no daemon:** o dispositivo fica registrado como `online`
      (visível depois pela UI do PC; por ora confirmável no log/estado).
      → OK (hw 2026-06-04): `presenca_marcar(online=True)` no `hello`; ficou
        `online` de forma contínua (1 conexao established na 8765).
- [x] **A3. Latência (o ponto-chave):** dispare um handoff de link **com o canal
      já aberto**. Deve abrir **quase instantâneo** (sem o ~1–3 s de antes).
      Compare com o fallback (A6).
      → OK (hw 2026-06-04): atalho da bolha (app YT Music) **pelo canal** —
        log `Descritor tipo='app'` 13:30:23,666 → `Caminho aberto` 13:30:23,755
        = **89 ms** no PC, sem nenhum `SEND -> daemon` antes (confirma que NÃO
        foi o fallback). Instantâneo. (Nota: a ferramenta 🔗 "Link da tela"
        falhou — Chrome não expõe a URL pela Acessibilidade; ver achado abaixo.)
- [x] **A4. Heartbeat:** deixe o app ocioso > 20 s; o canal continua `online`
      (pings periódicos no log). Sem desconexões espúrias.
      → OK (hw 2026-06-04): canal ON por ~1min44s contínuos, atravessando ~5
        ciclos de heartbeat (20 s) sem cair. Confirma que a queda anterior aos
        ~20 s era a Samsung matando o Foreground Service (ver R4), não bug do
        heartbeat — com o serviço vivo o canal fica estável.
- [x] **A5. Reconnect + backoff:** desligue o Wi-Fi do celular por ~30 s e religue
      → o canal volta sozinho (log: OFF e depois ON). Backoff cresce até religar.
      → OK (hw 2026-06-04): o canal volta sozinho ao religar o Wi-Fi. **Bug
        achado+corrigido:** com a queda abrupta o TCP antigo ficava zumbi no PC
        (sem FIN/RST) e o app reconectava criando uma 2ª conexão → 2 established
        + risco de a conexão velha marcar o device offline. Fix no daemon: o
        `hello` da reconexão derruba o canal anterior e o `finally` só marca
        offline se a conexão ainda for a vigente. Validado: log mostra
        `Canal anterior derrubado na reconexao` + `Canal antigo descartado` e
        fica **1 só** established, presença estável.
- [x] **A6. Fallback `--send`:** **pare** a bolha (canal cai) e dispare um handoff
      pela share sheet → deve **funcionar mesmo assim** (abre via `--send`).
      → OK (hw 2026-06-04): bolha off (`Canal persistente OFF`, `established=0`),
        Compartilhar → o link abriu via fallback — log mostra `SEND -> daemon`
        (assinatura do `--send`, que o canal nunca emite) seguido de `URL aberta`.
- [~] **A7. Fila offline:** com o canal caindo no meio, o evento enfileirado deve
      ser entregue ao reconectar (não some).
      → por design (não testado à mão): `outbox` é `Channel.UNLIMITED` criado uma
        vez pela vida do processo e drenado no reconnect. Porém `send()` só
        enfileira quando `isOnline()`; offline conhecido cai no `--send`. A fila
        só retém itens enfileirados online que não drenaram antes da queda
        (janela estreita) — difícil disparar deterministicamente no hardware.
- [x] **A8. Sessão 0×1 preservada:** confirme que as janelas abrem na **tela
      visível** (o `--serve` roda no sshd/sessão 0, mas só repassa ao daemon).
      → OK (hw 2026-06-04): o handoff pelo canal abriu a janela do YT Music na
        tela do usuário (o `--serve` só repassou ao daemon na sessão interativa).

> **Achado (fora do escopo A, mas registrado):** a ferramenta da bolha
> 🔗 "Link da tela" não envia nada — `HandoffAccessibilityService.lastUrl` vem
> vazio porque o Chrome atual não expõe o texto do `url_bar` pela Acessibilidade
> (`ToolRunner` mostra toast "Nenhuma URL em foco" e retorna null). O caminho
> robusto de URL é **"Compartilhar → Ecossistema"** (lê `EXTRA_TEXT`, sem
> depender da Acessibilidade). A validar e, se preciso, melhorar a captura
> (ler `text`/`contentDescription` do nó, fallback a outros ids do Chrome).

---

## 4. Fase B no hardware — emparelhamento por QR + pinning

Prova o "parear e pronto" e a remoção da dívida de segurança.

### Pré-requisitos
- [x] **B-pre1.** sshd no PC já rodando (host key ed25519 existente em
      `C:\ProgramData\ssh\ssh_host_ed25519_key.pub`).
      → OK (hw 2026-06-04): fingerprint resolve via ssh-keyscan apesar da ACL
        (`SHA256:jvsIKkg41q+...`).
- [x] **B-pre2.** `qrcode` instalado no PC se for usar o QR pelo CLI
      (`pip install qrcode[pil]`); ou usar a UI do PC quando existir.
      → OK (hw 2026-06-04): `qrcode` + `PIL` presentes. Helper `pair_hw.py`
        mostra o QR em **PNG** (mais fácil de escanear que o ASCII). **Bug de
        setup achado+corrigido:** o firewall não tinha regra p/ a porta **8766**
        (o `setup-windows.ps1` só abria a 22) → o celular não alcançava o
        pareamento. Regra `Handoff-Pair-In-TCP` adicionada ao script e criada no
        PC; alcançabilidade celular→8766 validada.

### Testes
- [x] **B1. Mostrar o QR:** `python agente.py --pair` no PC → mostra host, porta,
      user, fingerprint, token e o QR (ASCII no CLI).
      → OK (hw 2026-06-04): via `pair_hw.py` (PNG). host/port/user/fp/token/
        pair_port corretos no conteúdo do QR.
- [x] **B2. Escanear no app:** tocar **"Parear com QR"** → câmera abre → ler o QR.
      → OK (hw 2026-06-04): leitura do QR na tela do PC.
- [x] **B3. Permissão de câmera:** na 1ª vez o Android pede CAMERA → conceder.
      → OK (hw 2026-06-04): permissão concedida; câmera abriu e leu.
- [x] **B4. Geração da chave:** o app gera o par ed25519 (1ª vez) sem pedir nada
      ao usuário (nada de colar PEM).
      → OK (hw 2026-06-04): pubkey recebida `ssh-ed25519 AAAA...Xqe ecossistema`
        — **RISCO-1 (BouncyCastle↔sshj)** e **RISCO-2 (EncryptedSharedPreferences)**
        confirmados OK (chave gerada/guardada e usada).
- [x] **B5. Elevação (UAC):** no PC aparece **um** prompt de UAC para autorizar a
      chave → aceitar. A pública entra no `administrators_authorized_keys`.
      → OK (hw 2026-06-04): `autorizar_chave` retornou sucesso (só ocorre se o
        `add-authorized-key.ps1` elevado gravou a chave) → `_resp ok:true`.
- [x] **B6. Sucesso:** o app mostra "Pareado com <host>!" e o card de status vira
      **Conectado** (sem digitar IP nem chave).
      → OK (hw 2026-06-04): `PAREADO_OK name='SM-S721B'` no PC (confirmar visual
        no app + status Conectado).
- [~] **B7. Pinning ativo:** depois de pareado, um handoff conecta normalmente
      (fingerprint confere). Para provar o pinning, troque a host key do PC
      (`ssh-keygen -A` forçado/renomear) → a conexão deve **falhar** (host key não
      confere) em vez de aceitar cegamente.
      → POSITIVO OK (hw 2026-06-04): pós-pareamento o canal reconectou
        (`Canal persistente ON` 13:58:40) usando `PinnedHostKeyVerifier` — a host
        key real conferiu com o fingerprint do QR; 2 handoffs YT Music pelo canal.
        Prova que o fingerprint PC↔Android bate (mesmo cálculo wire SHA256).
      → NEGATIVO pendente: a troca da host key real é destrutiva (quebraria o
        sshd e o controle por SSH). Alternativa segura proposta: parear com um
        fingerprint propositalmente errado e ver o canal recusar (mesmo caminho
        de rejeição), depois re-parear certo. (opcional)
- [x] **B8. Token de uso único / janela:** após parear (ou após ~3 min), o canal
      de pareamento fecha; um 2º pareamento exige novo `--pair` (novo token).
      → OK (hw 2026-06-04): após o `PAREADO_OK`, o `servir_pareamento` retornou e
        a porta 8766 parou de escutar (`Listen=0`). Um novo pareamento exige novo
        `--pair`/`pair_hw.py` (novo token via `gerar_token()`).
- [ ] **B9. Token inválido:** apontar o app para um QR com token adulterado →
      pareamento recusado ("token invalido").
      → pendente no hardware (coberto em DEV-B2: token errado → `{"ok":false,
        "erro":"token invalido"}`). Testável com um QR de token adulterado.
        (opcional)
- [x] **B10. Convivência com legado:** uma config antiga (chave colada, sem
      fingerprint) continua funcionando (cai no verificador promíscuo de fallback).
      → OK (hw 2026-06-04): **antes** do pareamento o canal já subia e fazia
        handoff com a config legada (sem fingerprint → `PromiscuousVerifier`).
        Toda a Fase A (A1–A8) rodou nesse modo legado antes do QR.

---

## 5. Regressão / robustez

- [ ] **R1. `--send` puro** (sem canal): handoff via share sheet ainda abre no PC.
- [ ] **R2. `--list-apps`** continua retornando o JSON de apps do PC.
- [ ] **R3. SFTP** (enviar arquivo) abre na pasta `Ecossistema` e no app padrão.
- [~] **R4. App morto pela Samsung** → Foreground Service volta e o canal religa.
      → CONFIRMADO o problema (hw 2026-06-04): a Samsung **matou** o Foreground
        Service (a bolha sumiu sozinha) e o canal NÃO religou sozinho — ficou
        offline até religar manualmente. **Ação pendente:** isentar o app da
        otimização de bateria (whitelist) e/ou reforçar o serviço (START_STICKY +
        REQUEST_IGNORE_BATTERY_OPTIMIZATIONS) para sobreviver/religar sozinho.
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

**A pronto:** ✅ (hw 2026-06-04)
- [x] Canal sobe e fica `online` com heartbeat estável (A1, A2, A4).
- [x] Handoff perceptivelmente **instantâneo** com o canal aberto (A3) — 89 ms.
- [x] Reconnect automático e fallback `--send` funcionando (A5, A6).

**B pronto:** ✅ (hw 2026-06-04; falta só o B7 negativo opcional)
- [x] Parear com QR sem digitar IP nem colar chave (B1–B6).
- [~] Pinning ativo (B7): positivo provado (host key confere pós-pareamento); o
      negativo (host key trocada → recusada) fica como teste seguro opcional.
- [x] Legado segue funcionando (B10).
