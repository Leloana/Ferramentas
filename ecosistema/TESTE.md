# Próximos passos — Testar o Ecossistema (Marco 1)

> Checklist para validar tudo quando você estiver no **PC de casa** (que tem
> Windows + Android Studio + o celular emparelhado). A ordem vai do que prova
> mais rápido (lado PC sozinho) até o fluxo completo com o app nativo.
>
> Nada disso foi testado de verdade ainda — só sintaxe/lógica. Marque `[x]`
> conforme for validando.

---

## Fase A — Agente Windows sozinho (sem celular)

Prova que o cérebro (tabela de equivalentes) funciona, isolado do transporte.

- [x] **A1. Python presente:** `python --version` no PC (precisa estar no PATH).
      → Python 3.12.10 no PATH. (validado 2026-06-03)
- [x] **A2. Config:** `copy config.example.json config.json` e ajuste os
      `mapeamento_caminhos` para pastas reais (ex.: Download, DCIM).
      → `config.json` criado mapeando para Documents/Pictures/Downloads reais.
- [x] **A3. Subir o daemon na sessão do usuário:**
      `wscript start-agente.vbs` — ou, pra ver o log na hora:
      `python agente.py --daemon` (deixa esse terminal aberto).
      → validado via `python agente.py --daemon` (ouvindo em 127.0.0.1:8765).
        A variante `wscript start-agente.vbs` ainda não foi testada (ver Fase B).
- [x] **A4. Link (outro terminal):**
      `echo {"tipo":"url","app_origem":"teste","dados":{"url":"https://example.com"},"timestamp":0} | python agente.py --send`
      → deve abrir o navegador **na sua tela** (não invisível).
      → `--send` → daemon → "URL aberta: https://example.com" (log confirma).
- [x] **A5. YouTube com timestamp:**
      descritor `tipo":"midia"` com `"url":"https://youtu.be/dQw4w9WgXcQ","pos_segundos":42`
      → abre `youtu.be/dQw4w9WgXcQ?t=42`.
      → alvo resolvido = `https://youtu.be/dQw4w9WgXcQ?t=42` (inclui forma `watch?v=`).
- [x] **A6. Pasta → Explorer:**
      `tipo":"pasta"` com um `caminho` que case com o `mapeamento_caminhos`
      → o Explorer abre na pasta mapeada do Windows.
      → `/storage/emulated/0/Download/` → `C:\Users\mf827\Downloads`; Explorer abriu.
- [x] **A7. Texto → clipboard:** `tipo":"texto"` → cola (Ctrl+V) e confere.
      → `Get-Clipboard` retornou o texto enviado (transporte completo).
- [x] **A8. Fallback:** descritor com `tipo` inexistente mas `dados.url` http
      → ainda abre no navegador (regra automática).
      → "Handoff: link (fallback)" disparou para tipo desconhecido.
- [x] **A9. Log:** confira `C:\Users\<voce>\.handoff\agente.log` (uma linha por evento).
      → log em `C:\Users\mf827\.handoff\agente.log`, uma linha por evento.
- [ ] **A10. Toast:** veja se aparece a notificação do Windows em cada ação
      (se não aparecer, não trava nada — é best-effort).
      → código executa sem erro; **falta confirmar visualmente** o toast na tela.

> Dica p/ Windows: montar o JSON no `cmd` é chato pelas aspas. Salve o descritor
> num arquivo `x.json` e use `type x.json | python agente.py --send`.

---

## Fase B — Auto-start e sessão correta

Prova a lição da Sessão 0×1 (o app tem que abrir na tela visível).

- [ ] **B1. Startup:** copie `start-agente.vbs` para
      `shell:startup` (cole no Win+R) e faça **logoff/login**.
- [ ] **B2. Confirme** que o daemon subiu sozinho (teste A4 sem subir nada antes).
- [ ] **B3. Teste o anti-padrão:** dispare `agente.py --once <json>` **por SSH**
      (sessão do sshd) e confirme que abre **invisível/errado** — é exatamente
      o motivo de usarmos `--send` + daemon. (Só pra entender, não é o fluxo bom.)

---

## Fase C — Ponte Termux (celular → PC, sem o app nativo)

Prova o transporte SSH real, antes de mexer no APK.

- [x] **C1. SSH do PC já configurado:** rodou o `setup-windows.ps1` como admin
      com a `-PhonePubKey` do celular? (OpenSSH + firewall 22 + chave autorizada).
      → sshd em `0.0.0.0:22`, firewall "Handoff SSH" (Any), chave do celular
        autorizada em `administrators_authorized_keys`. (validado 2026-06-03)
- [ ] **C2. Termux:** `~/.ssh/config` tem o alias `pc-remoto`
      (`cat ssh_config_termux >> ~/.ssh/config`) com o IP/HostName certo.
      → não usei o alias; testei com `ssh -i ~/.ssh/id_ed25519 mf827@192.168.15.6`.
- [x] **C3. Conexão crua:** `ssh pc-remoto "echo ok"` → imprime `ok`.
      → de dentro do celular, `ssh mf827@192.168.15.6 "echo ..."` → `PC_OK_FROM_PHONE`.
- [ ] **C4. Instalar scripts:**
      `cp termux-url-opener termux-handoff ~/bin/ && chmod +x ~/bin/termux-*`
      → não instalados (o transporte que eles usam já está provado por `ssh` cru).
- [ ] **C5. Ajuste o `PC_AGENTE`** nos dois scripts (caminho do `agente.py` no PC).
      → não precisa: o default já é o caminho real (`...\ecosistema\agente.py`).
- [x] **C6. Daemon rodando no PC** (Fase A/B).
- [ ] **C7. Link genérico:** `termux-handoff --url "https://example.com"`
      → abre no PC.
- [ ] **C8. Share Sheet:** num app qualquer → Compartilhar → **Termux** →
      `termux-url-opener` envia → abre no PC. Teste com um link do YouTube.
- [ ] **C9. Pasta/arquivo/texto/mapa:** `termux-handoff --pasta /storage/emulated/0/DCIM`,
      `--texto`, `--mapa "Av Paulista"`.
- [ ] **C10. Fora da Wi-Fi (Tailscale):** troque o `HostName` no `~/.ssh/config`
      pelo IP `100.x` e repita C7 no 4G/5G.

---

## Fase D — App Android nativo (APK)

Substitui o Termux pelo gesto. Mesmo transporte (SSH → `agente.py --send`),
então se a Fase C passou, o lado PC já está provado.

### D1. Build
- [x] Wrapper gerado (`gradle-wrapper.jar` 8.11.1 baixado; `gradlew`/`.bat` presentes).
- [x] Correções de código aplicadas antes do build:
      - `net.i2p.crypto:eddsa` adicionado (sshj precisa p/ a chave **ed25519** — senão a auth falha em runtime).
      - Pedido de `POST_NOTIFICATIONS` em runtime na `MainActivity` (Android 13+, p/ a notificação persistente do FGS aparecer).
- [x] **SDK destravado:** usado o SDK gravável `%LOCALAPPDATA%\Android\Sdk`
      (licenças aceitas, tem `build-tools/34.0.0` que o AGP 8.7.3 pede). O antigo em
      `Program Files (x86)` era read-only/sem licença → trocado via `local.properties`.
- [x] **2 erros de compilação corrigidos** (scaffold nunca tinha compilado):
      - `SshHandoffTransport`: import era `net.schmizz.sshj.transport.verify` (inexistente)
        → correto é `...transport.verification.PromiscuousVerifier`.
      - `mergeDebugJavaResource`: colisão `META-INF/versions/**/OSGI-INF/MANIFEST.MF`
        entre bcprov/bcpkix/bcutil (via sshj) → adicionado ao `packaging.excludes`.
- [x] **`assembleDebug` → BUILD SUCCESSFUL** (`app-debug.apk`, ~13,8 MB). (2026-06-03)
- [x] Entregue no celular via scp (porta 8022): `/sdcard/Download/ecossistema-marco1.apk`.
      *(adb sem device; instalar tocando no arquivo. `installDebug` se conectar USB.)*

### D2. Configuração no app (tela inicial)
- [ ] **Conexão com o PC:** host (IP LAN ou `100.x`), usuário Windows, porta 22,
      caminho do `agente.py`, e cole a **chave privada PEM** (`id_ed25519` cuja
      pública já está autorizada no PC). → **Salvar conexão**.
- [ ] **Permissões** (botões abrem as telas do sistema):
      1. Sobreposição (overlay)
      2. Acessibilidade (ativar o serviço "Ecossistema")
      3. Acesso de uso (UsageStats)
      4. Ignorar otimização de bateria
- [ ] **Iniciar serviço + overlay** (deve aparecer a notificação persistente e
      o "handle" flutuante).

### D3. Fluxos do Marco 1
- [ ] **Teste rápido (na própria UI):** botões "Testar: abrir link" e
      "Testar: YouTube com timestamp" → abrem no PC. (Valida SSH + agente.)
- [ ] **Share target:** Compartilhar um link de qualquer app → **Ecossistema**
      → abre no PC (YouTube vira `midia` com `t=` se a URL trouxer o tempo).
- [ ] **Gesto "arrastar pro canto":** abra o Chrome/YouTube numa página, arraste
      o handle até um canto da tela e solte → o app em foco continua no PC.

### D4. Robustez
- [ ] Matar o app e ver se o Foreground Service volta (otimização da Samsung).
- [ ] Testar com o PC **suspenso/desligado** → app deve dar toast de erro, não travar.
- [ ] Testar fora da Wi-Fi (Tailscale) com o host `100.x`.

---

## Bugs/limitações já conhecidos (esperados nesta fase)

- **Host key SSH** aceita qualquer (`PromiscuousVerifier`) → pinning é TODO.
- **Timestamp do YouTube**: só lê `t=` se já estiver na URL; player ainda não é lido.
- **PC → Android** (sentido inverso) ainda não existe — é a próxima fase.
- Montar JSON no `cmd` do Windows é chato → use arquivo + `type ... |`.

---

## Critério de "Marco 1 pronto" (PLANO.md §5)

Os **3 casos** funcionando de forma **visível e confiável**, com o agente na
sessão do usuário:
- [x] YouTube com timestamp — *celular → PC real: `youtu.be/dQw4w9WgXcQ?t=42` abriu na tela*
- [x] URL/aba no navegador — *celular → PC real: link abriu na tela*
- [x] Pasta → Explorer — *celular → PC real: Explorer abriu em `C:\Users\mf827\Downloads`*

> **MARCO 1 PROVADO ponta a ponta (2026-06-03).** Loop real validado:
> PC →(ssh:8022)→ celular (Termux) →(ssh:22, chave ed25519 do celular)→ sshd do PC
> → `agente.py --send` → daemon(8765) → app abre **na tela visível** do usuário.
> O usuário confirmou visualmente as janelas abrindo (navegador + Explorer).
> Não precisou dos scripts Termux nem do APK: o `ssh` cru já exercita o mesmo
> transporte que o `SshHandoffTransport` do app usará.
>
> Pendências: **APK (Fase D)** travado no provisionamento do SDK (licenças/
> read-only), não no código — ver Fase D. Toast do Windows (A10) não conferido
> visualmente. Pinning de host key (PromiscuousVerifier) segue TODO.
