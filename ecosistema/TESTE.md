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

- [ ] **C1. SSH do PC já configurado:** rodou o `setup-windows.ps1` como admin
      com a `-PhonePubKey` do celular? (OpenSSH + firewall 22 + chave autorizada).
- [ ] **C2. Termux:** `~/.ssh/config` tem o alias `pc-remoto`
      (`cat ssh_config_termux >> ~/.ssh/config`) com o IP/HostName certo.
- [ ] **C3. Conexão crua:** `ssh pc-remoto "echo ok"` → imprime `ok`.
- [ ] **C4. Instalar scripts:**
      `cp termux-url-opener termux-handoff ~/bin/ && chmod +x ~/bin/termux-*`
- [ ] **C5. Ajuste o `PC_AGENTE`** nos dois scripts (caminho do `agente.py` no PC).
- [ ] **C6. Daemon rodando no PC** (Fase A/B).
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
- [ ] Abrir a pasta `android/` no **Android Studio** (ele gera o `gradle-wrapper.jar`).
- [ ] Ou via CLI: `cd android && gradle wrapper --gradle-version 8.11.1 && ./gradlew assembleDebug`.
- [ ] Corrigir o que o **Lint/compilador** apontar (scaffold não foi compilado).
- [ ] Instalar: `./gradlew installDebug` (ou arrastar o APK pro celular).

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
- [x] YouTube com timestamp — *resolução + transporte ok; falta confirmar visualmente na sessão de Startup (Fase B)*
- [x] URL/aba no navegador — *resolução + transporte ok; idem*
- [x] Pasta → Explorer — *resolução + transporte ok; Explorer abriu nesta sessão*

> Nota (2026-06-03): Fase A validada end-to-end nesta máquina via daemon em
> primeiro plano (`python agente.py --daemon`) + `--send`. Falta apenas a
> confirmação **visual na sessão interativa de Startup** (Fase B) e o toast (A10).
