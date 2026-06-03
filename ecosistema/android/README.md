# App Android — Ecossistema (Marco 1)

App nativo (Kotlin + Jetpack Compose) que substitui a ponte Termux: leva o
**gesto** "arrastar pro canto" e o **estado** do app em foco no handoff para o
PC. Espelha o protocolo do [`agente.py`](../agente.py) (descritor JSON, 1 por
linha) e usa o **mesmo transporte** da ponte Termux: SSH executando
`python agente.py --send` com o descritor na STDIN.

> Scaffold do Marco 1: estrutura completa + lógica central. Foi escrito sem
> ambiente de build à mão; **compile no PC de casa** (Android Studio) e ajuste
> o que o Lint apontar antes de publicar.

## Estrutura

```
android/
├── settings.gradle.kts, build.gradle.kts, gradle.properties
├── gradle/libs.versions.toml         (version catalog)
└── app/
    ├── build.gradle.kts
    └── src/main/
        ├── AndroidManifest.xml
        ├── res/ (strings, theme, icone vetorial, config de acessibilidade)
        └── kotlin/com/firepot/ecossistema/
            ├── MainActivity.kt              UI: conexao + permissoes + testes
            ├── EcossistemaApp.kt            Application
            ├── model/Descriptor.kt          descritor de handoff (== agente.py)
            ├── data/Settings.kt             DataStore: host/user/porta/chave/path
            ├── net/HandoffTransport.kt      interface de transporte
            ├── net/SshHandoffTransport.kt   SSH (sshj) -> agente.py --send
            ├── handoff/HandoffManager.kt    classifica conteudo + envia + toast
            ├── service/HandoffForegroundService.kt   canal vivo + sobe overlay
            ├── service/HandoffAccessibilityService.kt le app/URL em foco
            ├── overlay/CornerOverlayService.kt        gesto "arrastar pro canto"
            └── share/ShareReceiverActivity.kt         "Compartilhar -> Ecossistema"
```

## Como buildar (no PC com Android SDK)

```bash
cd android
# Gera o gradle wrapper (jar nao versionado neste scaffold):
gradle wrapper --gradle-version 8.11.1
# Ou abra a pasta no Android Studio (ele regenera o wrapper sozinho).
./gradlew assembleDebug
# APK em app/build/outputs/apk/debug/app-debug.apk
```

`local.properties` (com `sdk.dir=...`) é criado pelo Android Studio.

## Configuração no app (primeira vez)

1. **Conexão com o PC:** host (IP LAN ou `100.x` do Tailscale), usuário do
   Windows, porta SSH (22), caminho do `agente.py`, e a **chave privada PEM**
   (a mesma `id_ed25519` cuja pública já está autorizada pelo `setup-windows.ps1`).
2. **Permissões do gesto:** overlay, Acessibilidade, Acesso de uso, e ignorar
   otimização de bateria (botões abrem as telas do sistema).
3. **Iniciar serviço + overlay.**

No PC, o `agente.py --daemon` precisa estar rodando na sessão do usuário
(`start-agente.vbs`). O fluxo é idêntico ao da ponte Termux — só troca o
disparador.

## Fluxos cobertos (Marco 1)

- **Compartilhar link/texto → Ecossistema:** `ShareReceiverActivity` classifica
  (YouTube→`midia` com `t=`, http→`url`, resto→`texto`) e envia.
- **Arrastar o handle pro canto:** `CornerOverlayService` lê a URL em foco via
  `HandoffAccessibilityService` e dispara o handoff (YouTube/navegador).

## Limitações conhecidas / TODO

- **Host key SSH** aceita qualquer chave (`PromiscuousVerifier`). TODO: pinning
  / emparelhamento + `known_hosts`.
- **Timestamp exato do player** do YouTube ainda não é lido (só `t=` presente na
  URL). Evolução: ler o estado do player via acessibilidade.
- **PC → Android** (sentido inverso) é fase seguinte.
- Falta `gradle-wrapper.jar` (binário) — gerar com `gradle wrapper`.
