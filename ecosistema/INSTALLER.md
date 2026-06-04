# Plano de Criação do MSI Installer — Ecossistema Híbrido

> **Objetivo:** Empacotar o Ecossistema Híbrido (agente Windows + scripts de setup +
> app Android) em um instalador `.msi` profissional para distribuição e instalação
> em PCs Windows **sem Python instalado** — zero dependências de runtime.

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Impacto no App Android](#2-impacto-no-app-android)
3. [Pré-requisitos](#3-pré-requisitos)
4. [Fase 1 — Empacotar o Python com PyInstaller](#4-fase-1--empacotar-o-python-com-pyinstaller)
5. [Fase 2 — Estruturar o Projeto WiX](#5-fase-2--estruturar-o-projeto-wix)
6. [Fase 3 — Escrever o Arquivo .wxs](#6-fase-3--escrever-o-arquivo-wxs)
7. [Fase 4 — Compilar o MSI](#7-fase-4--compilar-o-msi)
8. [Fase 5 — Pós-Instalação e CustomActions](#8-fase-5--pós-instalação-e-customactions)
9. [Fase 6 — Testes e Validação](#9-fase-6--testes-e-validação)
10. [Estrutura Final do Instalador](#10-estrutura-final-do-instalador)
11. [Manutenção e Build Automatizado](#11-manutenção-e-build-automatizado)
12. [Apêndice](#12-apêndice)

---

## 1. Visão Geral

O instalador MSI deve:

- **Rodar em PCs sem Python.** O agente Python é compilado para .exe standalone
  via PyInstaller (`--onefile`). Zero dependências de runtime no PC alvo.
- Instalar o **agente Windows** (`ecossistema-agente.exe`) em `Program Files`.
- Instalar scripts auxiliares (`setup-windows.ps1`, `start-agente.vbs`).
- Instalar o **projeto Android APK** (`android/` — opcional, como recurso).
- Configurar **auto-start** do agente no login (via `HKCU\Run`).
- Registrar atalhos no **Menu Iniciar**.
- Registrar chave de **desinstalação** no Windows (Padrão do MSI).
- Oferecer CustomAction para **configurar firewall** (porta do daemon 8765) —
  alternativa à execução manual de `setup-windows.ps1`.

### O que **não** faz parte do MSI

- Instalação/configuração do **OpenSSH Server** (`setup-windows.ps1` faz isso e
  exige privilégios de ADMIN + interação do usuário com a chave SSH). O MSI pode
  **disparar** o script como ação pós-instalação opcional, mas não substituí-lo.
- Configuração do **mapeamento de caminhos** (`config.json`). O MSI copia o
  `config.example.json`; o usuário edita manualmente.

---

## 2. Impacto no App Android

### 2.1 Sim, a interação muda — e precisa ser atualizada no lado Android

Hoje o app Android (Termux) chama o agente assim:

```bash
echo '<descritor>' | ssh pc-remoto "python C:\Users\mf827\Documents\Ferramentas\ecosistema\agente.py --send"
```

Com o MSI instalado, o comando passa a ser:

```bash
echo '<descritor>' | ssh pc-remoto "ecossistema-agente.exe --send"
```

**Mudanças obrigatórias no lado Android:**

| O que muda | Antes (dev) | Depois (MSI) |
|---|---|---|
| **Comando no SSH** | `python ...\agente.py --send` | `ecossistema-agente.exe --send` |
| **Caminho do executável** | Pasta do repositório clonado | `C:\Program Files\Ecossistema\ecossistema-agente.exe` |
| **Dependência de runtime** | Python 3.12+ necessário no PC | Nenhuma (executável standalone) |
| **Auto-start** | VBS na pasta Startup (manual) | Registro `HKCU\Run` (automático via MSI) |

### 2.2 O que precisa ser alterado

#### a) `ssh_config_termux` (no celular)

O alias `pc-remoto` continua valendo. O que muda é o **comando remoto** no
`termux-url-opener` e no `termux-handoff`:

```bash
# Antes
echo "$1" | ssh pc-remoto "python C:\...\ecosistema\agente.py --send"

# Depois
echo "$1" | ssh pc-remoto "ecossistema-agente.exe --send"
```

#### b) App Android nativo (`android/`)

O APK nativo (Kotlin/Compose) que está sendo desenvolvido envia descritores via
SSH. Ele deve ser atualizado para chamar `ecossistema-agente.exe --send` em vez
de `python agente.py --send`. O caminho do executável também muda — o MSI
registra o `InstallPath` em `HKLM\Software\Ecossistema`, e o APK pode ler isso
via execução remota de:

```bash
reg query HKLM\Software\Ecossistema /v InstallPath
```

Ou simplesmente hardcodar `"ecossistema-agente.exe"` (já que o `PATH` do
Windows inclui `C:\Program Files\Ecossistema\` se configurado no MSI).

#### c) Scripts auxiliares (`start-agente.vbs`, `start-daemon.vbs`)

Ambos atualmente hardcodam caminhos absolutos para `pythonw.exe` e para o
script `.py`. Com o MSI, esses VBS deixam de ser necessários — o auto-start
passa a ser via `HKCU\Run` apontando diretamente para o `.exe`.

Se quiser manter os VBS como fallback, eles devem ser atualizados para:

```vbscript
pyw = "C:\Program Files\Ecossistema\ecossistema-agente.exe"
script = "--daemon"
' 0 = janela oculta ; False = nao espera terminar
shell.Run """" & pyw & """ " & script, 0, False
```

### 2.3 Compatibilidade reversa

O protocolo de handoff (formato do descritor JSON, porta TCP 8765) **não muda**.
A troca de `python agente.py --send` → `ecossistema-agente.exe --send` é
transparente para o formato dos dados. O Android continua mandando o mesmo JSON;
o agente processa do mesmo jeito.

**Resumo:** o app Android precisa de uma atualização **no comando SSH**, mas
o protocolo, o formato do descritor e a lógica do agente permanecem idênticos.

---

## 3. Pré-requisitos

### 3.1 Ferramentas

| Ferramenta | Onde obter | Função |
|---|---|---|
| **Python 3.12+** | python.org | Runtime para rodar o PyInstaller |
| **PyInstaller** | `pip install pyinstaller` | Empacota Python → .exe standalone |
| **WiX Toolset v4** | [`dotnet tool install --global wix`](https://wixtoolset.org/) | Compila .wxs → .msi |
| **.NET SDK 6+** | dotnet.microsoft.com | Necessário para o WiX v4 (CLI) |

### 3.2 Verificação

```powershell
python --version
pip show pyinstaller
wix --version    # wixtoolset v4
```

### 3.3 Estrutura de diretórios de build

Dentro de `ecosistema/`, criar uma pasta `installer/` para isolar os artefatos:

```
ecosistema/
├── installer/
│   ├── build/          # artefatos temporários (PyInstaller, heat output)
│   ├── dist/           # .exe compilado + MSI final
│   ├── src/            # arquivos .wxs e .wxi
│   └── assets/         # ícones, banners
├── agente.py
├── ...
└── INSTALLER.md
```

---

## 4. Fase 1 — Empacotar o Python com PyInstaller

### 4.1 Instalar PyInstaller

```powershell
pip install pyinstaller
```

### 4.2 Compilar o agente.py em um único .exe

```powershell
pyinstaller --onefile --windowed --name ecossistema-agente `
  --icon installer/assets/icone.ico `
  --add-data "config.example.json;." `
  --distpath installer\dist `
  --workpath installer\build `
  agente.py
```

**Flags explicadas:**

| Flag | Efeito |
|---|---|
| `--onefile` | Gera um único .exe (extrai-se na execução) |
| `--windowed` | Suprime console (roda como daemon invisível) |
| `--name` | Nome do executável de saída |
| `--icon` | Ícone do .exe (criar um .ico com ferramenta como GIMP ou conversor online) |
| `--add-data` | Embuti `config.example.json` dentro do .exe (o pyinstaller extrai ao rodar) |
| `--distpath` | Pasta de saída do executável final |
| `--workpath` | Pasta temporária de trabalho |

> Nota sobre `--windowed`: como `agente.py` tem argumentos de linha de comando
> (`--send`, `--once`, `--list-apps`), pode ser útil **também** gerar uma
> variante `--console` (sem `--windowed`) para debug, ou usar duas entradas
> no Menu Iniciar (uma "Agente (daemon)" e outra "Agente (terminal)").

### 4.3 Compilar receiver.py (legado)

```powershell
pyinstaller --onefile --windowed --name ecossistema-receiver `
  --distpath installer\dist --workpath installer\build receiver.py
```

### 4.4 Testar o executável gerado

```powershell
# Teste do daemon (janela invisível)
installer\dist\ecossistema-agente.exe --daemon

# Teste de envio (TCP para o daemon)
installer\dist\ecossistema-agente.exe --send '{"tipo":"url","dados":{"url":"https://example.com"}}'

# Teste de listagem de apps
installer\dist\ecossistema-agente.exe --list-apps

# Teste once (abre direto, sem daemon)
installer\dist\ecossistema-agente.exe --once '{"tipo":"url","dados":{"url":"https://example.com"}}'
```

### 4.5 Empacotar setup-windows.ps1 como recurso separado

O `setup-windows.ps1` não precisa ser compilado. Será copiado como arquivo texto
no MSI para `Program Files\Ecossistema\`.

---

## 5. Fase 2 — Estruturar o Projeto WiX

### 5.1 Instalar WiX Toolset v4

```powershell
dotnet tool install --global wix
```

### 5.2 Criar os arquivos fonte do WiX

Dentro de `installer/src/`:

```
installer/
├── src/
│   ├── installer.wxs        # arquivo principal
│   ├── fragments.wxi        # include de componentes (opcional)
│   └── ui.wxs               # customização de interface (opcional)
├── assets/
│   ├── icone.ico             # ícone do atalho
│   ├── banner.bmp            # banner do instalador (topo)
│   └── dialog.bmp            # imagem de fundo dos diálogos
├── build/
├── dist/
└── ...
```

### 5.3 Gerar ícone .ico

Criar um ícone com resoluções 16, 32, 48, 64, 128 e 256 pixels. Ferramentas:

- **GIMP** + plugin `ico`
- **ImageMagick**: `magick convert logo.png -define icon:auto-resize=16,32,48,64,128,256 icone.ico`
- Conversores online (avocar imagens simples)

---

## 6. Fase 3 — Escrever o Arquivo .wxs

> O WiX v4 usa XML descrevendo **Componentes** (arquivos), **Features** (grupos
> selecionáveis), **Diretórios** (estrutura de pastas) e **CustomActions**
> (ações com código nativo/PowerShell).

### 6.1 Modelo conceitual do .wxs

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package
    Name="Ecossistema Híbrido"
    Version="1.0.0"
    Manufacturer="Ecossistema"
    UpgradeCode="SEU-GUID-AQUI"
    Scope="perMachine"
    Languages="pt-BR">

    <!-- Ícone do instalador no Add/Remove Programs -->
    <Icon Id="icon.ico" SourceFile="..\assets\icone.ico" />
    <Property Id="ARPPRODUCTICON" Value="icon.ico" />

    <!-- Estrutura de diretórios -->
    <StandardDirectory Id="ProgramFiles64Folder">
      <Directory Id="EcossistemaDir" Name="Ecossistema">
        <Directory Id="AndroidDir" Name="android" />
      </Directory>
    </StandardDirectory>

    <StandardDirectory Id="ProgramMenuFolder">
      <Directory Id="EcossistemaShortcutsDir" Name="Ecossistema Híbrido" />
    </StandardDirectory>

    <!-- Componentes e arquivos -->
    <Feature Id="Main" Title="Ecossistema" Level="1"
             Description="Agente Windows do Ecossistema Híbrido">

      <!-- Componente: executável principal -->
      <Component Directory="EcossistemaDir" Guid="SEU-GUID-COMP">
        <File Id="agente.exe" Source="..\dist\ecossistema-agente.exe" />
        <File Id="receiver.exe" Source="..\dist\ecossistema-receiver.exe" />
        <File Id="config.example.json"
              Source="..\..\config.example.json" />
        <File Id="setup-windows.ps1"
              Source="..\..\setup-windows.ps1" />
        <File Id="start-agente.vbs"
              Source="..\..\start-agente.vbs" />
        <File Id="README.md" Source="..\..\README.md" />
        <File Id="PLANO.md" Source="..\..\PLANO.md" />
        <File Id="INSTALLER.md" Source="..\..\INSTALLER.md" />
      </Component>

      <!-- Componente: atalhos no Menu Iniciar -->
      <Component Directory="EcossistemaShortcutsDir" Guid="SEU-GUID-SHORTCUTS">
        <Shortcut Id="AgenteDaemon" Name="Agente Ecossistema"
                  Target="[EcossistemaDir]ecossistema-agente.exe"
                  Arguments="--daemon"
                  IconFile="[EcossistemaDir]ecossistema-agente.exe"
                  IconIndex="0" />
        <Shortcut Id="Uninstall" Name="Desinstalar Ecossistema"
                  Target="[System64Folder]msiexec.exe"
                  Arguments="/x [ProductCode]" />
        <RemoveFolder Id="RemoveEcossistemaShortcutsDir"
                      Directory="EcossistemaShortcutsDir"
                      On="uninstall" />
      </Component>

      <!-- Componente: auto-start no login do usuário -->
      <Component Directory="EcossistemaDir" Guid="SEU-GUID-AUTOSTART">
        <Shortcut Id="AutoStartAgente"
                  Directory="ProgramMenuFolder"
                  Name="Ecossistema Agente"
                  Target="[EcossistemaDir]ecossistema-agente.exe"
                  Arguments="--daemon"
                  WorkingDirectory="EcossistemaDir">
          <ShortcutProperty Key="System.AppUserModel.ID"
                           Value="Ecossistema.Agente" />
        </Shortcut>
      </Component>

      <!-- Componente: projeto Android (opcional) -->
      <Component Directory="AndroidDir" Guid="SEU-GUID-ANDROID">
        <!-- O WiX não suporta recursão fácil; usar harvest (heat) -->
      </Component>
    </Feature>

    <!-- Registry: chave de configuração -->
    <Property Id="INSTALLDIR" Value="[EcossistemaDir]" />
    <RegistryKey Root="HKLM" Key="Software\Ecossistema">
      <RegistryValue Type="string" Name="InstallPath"
                     Value="[EcossistemaDir]" />
    </RegistryKey>

    <!-- CustomAction: setup-windows.ps1 (pós-instalação opcional) -->
    <!-- Ver seção 8 -->
  </Package>
</Wix>
```

### 6.2 GUIDs: quando gerar novos

Cada `{GUID}` no WiX deve ser único. Gerar com PowerShell:

```powershell
[guid]::NewGuid().ToString("B").ToUpper()
```

- **UpgradeCode:** fixo para sempre (identifica o produto).
- **Component GUIDs:** fixos por versão do componente (WiX cuida disso).
- **ProductCode:** novo a cada versão (o WiX gera automaticamente se omitir).

### 6.3 Harvest do diretório android/ com heat

O projeto Android tem muitos arquivos aninhados. O WiX v4 fornece o **heat**
para mapear pastas automaticamente em um arquivo `.wxs` separado:

```powershell
heat dir ..\..\android -o fragments.wxs -dr AndroidDir -cg AndroidComponents `
  -gg -g1 -sfrag -srd -var var.AndroidSourcePath
```

Depois, incluir no `installer.wxs`:

```xml
<FragmentRef Id="AndroidComponents" />
```

E passar o caminho da fonte no build:

```powershell
wix build installer.wxs fragments.wxs -d AndroidSourcePath="..\..\android"
```

---

## 7. Fase 4 — Compilar o MSI

### 7.1 Comando completo de build

```powershell
# Na pasta installer/
wix build src\installer.wxs -o dist\Ecossistema-v1.0.0.msi `
  -d AndroidSourcePath="..\android" `
  -arch x64
```

### 7.2 Build com variantes (x86 / x64)

```powershell
wix build src\installer.wxs -o dist\Ecossistema-v1.0.0-x64.msi -arch x64
wix build src\installer.wxs -o dist\Ecossistema-v1.0.0-x86.msi -arch x86
```

### 7.3 Assinatura digital (opcional, mas recomendado)

```powershell
signtool sign /fd SHA256 /a /f "certificado.pfx" /p "senha" `
  dist\Ecossistema-v1.0.0.msi
```

### 7.4 Script de build automatizado

Criar `installer/build-msi.ps1`:

```powershell
<#
.SYNOPSIS
  Compila o MSI do Ecossistema Híbrido.
.DESCRIPTION
  1. Roda PyInstaller para gerar .exe
  2. Roda heat para mapear android/
  3. Compila o .wxs com WiX v4
  4. (Opcional) Assina o MSI
#>

param(
  [string]$Version = "1.0.0",
  [string]$Config  = "x64",
  [switch]$Sign
)

$ErrorActionPreference = "Stop"
$Root   = Resolve-Path "$PSScriptRoot\.."
$Dist   = "$PSScriptRoot\dist"
$Build  = "$PSScriptRoot\build"
$Src    = "$PSScriptRoot\src"

# 1. PyInstaller
Write-Host "[1/4] Empacotando agente.py (standalone, sem Python)..." -ForegroundColor Cyan
& pyinstaller --onefile --windowed --name ecossistema-agente `
  --add-data "$Root\config.example.json;." `
  --distpath "$Dist" --workpath "$Build" "$Root\agente.py"
if (-not (Test-Path "$Dist\ecossistema-agente.exe")) {
  throw "Falha no PyInstaller"
}

# 2. Heat (android/)
Write-Host "[2/4] Harvest android/ com heat..." -ForegroundColor Cyan
& wix heat dir "$Root\android" -o "$Src\android-fragments.wxs" `
  -dr AndroidDir -cg AndroidComponents -gg -g1 -sfrag -srd `
  -var var.AndroidSourcePath
if ($LASTEXITCODE -ne 0) { throw "heat falhou" }

# 3. WiX build
Write-Host "[3/4] Compilando MSI..." -ForegroundColor Cyan
& wix build "$Src\installer.wxs" "$Src\android-fragments.wxs" `
  -o "$Dist\Ecossistema-v$Version-$Config.msi" `
  -d AndroidSourcePath="$Root\android" `
  -arch $Config
if ($LASTEXITCODE -ne 0) { throw "wix build falhou" }

# 4. Assinatura
if ($Sign) {
  Write-Host "[4/4] Assinando MSI..." -ForegroundColor Cyan
  & signtool sign /fd SHA256 /a `
    "$Dist\Ecossistema-v$Version-$Config.msi"
}

Write-Host "OK: $Dist\Ecossistema-v$Version-$Config.msi" -ForegroundColor Green
```

---

## 8. Fase 5 — Pós-Instalação e CustomActions

### 8.1 CustomAction: disparar setup-windows.ps1

O script `setup-windows.ps1` configura OpenSSH Server e o firewall. Só faz
sentido executar como **ADMIN** e de forma **opt-in** (o usuário escolhe).

WiX v4 + `WixToolset.Bal.wixext` (BA) ou usando `PowerShell` via
`WixToolset.Util.wixext`:

```xml
<!-- Util: PowerShell script de pós-instalação -->
<Component Directory="EcossistemaDir" Guid="SEU-GUID">
  <File Id="SetupPs1" Source="$(sys.SOURCEFILEPATH)" />
</Component>

<CustomAction Id="RunSetup"
              BinaryKey="Wix4PowerShell"
              Execute="deferred"
              Impersonate="no"
              Return="check" />

<!-- Ou usando o suporte nativo do WiX v4: -->
<StandardAction Id="RunSetupPowershell"
                Execute="deferred"
                Impersonate="no"
                Return="ignore">
  <Command Prompt="yes" Arguments="..." />
</StandardAction>
```

**Decisão de design:** Manter `setup-windows.ps1` como arquivo no `Program Files`
e documentar no README que o usuário deve rodá-lo manualmente como Admin. O MSI
apenas copia o script — evita elevação inesperada de privilégio e falhas.

### 8.2 Auto-start do agente no login

Duas abordagens:

#### A. Pasta Startup do usuário atual (já usada hoje)

```xml
<StandardDirectory Id="AppDataFolder">
  <Directory Id="StartupFolder" Name="Microsoft\Windows\Start Menu\Programs\Startup">
    <Component Guid="SEU-GUID" Directory="StartupFolder">
      <Shortcut Id="AutoStartVBS"
                Name="Ecossistema Agente"
                Target="[EcossistemaDir]start-agente.vbs"
                IconFile="[EcossistemaDir]ecossistema-agente.exe"
                IconIndex="0"
                Show="minimized" />
      <RemoveFolder Id="RemoveStartupShortcut" On="uninstall" />
      <RegistryValue Root="HKCU" Key="Software\Ecossistema"
                     Name="AutoStartInstalled" Type="integer" Value="1" />
    </Component>
  </Directory>
</StandardDirectory>
```

#### B. Registro Run (HKCU\Software\Microsoft\Windows\CurrentVersion\Run)

```xml
<RegistryKey Root="HKCU"
             Key="Software\Microsoft\Windows\CurrentVersion\Run">
  <RegistryValue Type="string"
                 Name="EcossistemaAgente"
                 Value="[EcossistemaDir]ecossistema-agente.exe --daemon" />
</RegistryKey>
```

A abordagem **B** é mais limpa (um registro apenas), sem atalho visível na
Startup. Recomendada.

### 8.3 Firewall (porta do daemon 8765)

O daemon escuta em `127.0.0.1:8765`. Por ser **loopback**, não precisa de regra
de firewall (não é acessível externamente). O `setup-windows.ps1` cuida da
porta 22 (SSH), que é externa.

Nenhuma ação de firewall necessária no MSI.

### 8.4 Desinstalação

O MSI registra automaticamente desinstalação em
`HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall`.

Limpeza extra (opcional): uma CustomAction pode deletar `C:\Users\<user>\.handoff\`.

```xml
<CustomAction Id="CleanHandoffDir" Execute="deferred"
              Impersonate="yes" Return="ignore">
  <Command>rmdir /s /q "%USERPROFILE%\.handoff"</Command>
</CustomAction>
```

---

## 9. Fase 6 — Testes e Validação

### 9.1 Cenários de teste

| # | Cenário | Resultado esperado |
|---|---|---|
| 1 | Instalação limpa (PC sem Python) | MSI instala sem pedir runtime, atalhos criados, agente `--daemon` funciona |
| 2 | Desinstalação via Add/Remove Programs | Pastas removidas, auto-start removido, serviço não deixa resíduos |
| 3 | Instalação sobre versão anterior (upgrade) | Substitui arquivos sem quebrar configuração existente |
| 4 | Instalação sem privilégios admin (se `perUser`) | Instala só pro usuário, auto-start em HKCU |
| 5 | `ecossistema-agente --daemon` pós-instalação | Processo invisível rodando, TCP 8765 aberto |
| 6 | `ecossistema-agente --send '...'` | Daemon recebe e processa o descritor |
| 7 | `setup-windows.ps1` executado manualmente | OpenSSH + firewall configurados |

### 9.2 Ferramentas de validação

```powershell
# MSI internals (verificar componentes, arquivos, registry)
msiexec /a Ecossistema-v1.0.0.msi /qb TARGETDIR="C:\temp\extract"

# Log de instalação detalhado
msiexec /i Ecossistema-v1.0.0.msi /l*v install.log

# Validação WiX (best-practices)
wix verify Ecossistema-v1.0.0.msi

# Verificar tabelas internas do MSI
cscript C:\Windows\System32\msizap.wsf /t Ecossistema-v1.0.0.msi
```

### 9.3 Teste em VM

Sempre testar em uma **VM Windows limpa** (sem Python, sem pré-requisitos)
para validar que o executável standalone funciona isoladamente.

---

## 10. Estrutura Final do Instalador

### 10.1 Árvore de instalação (destino)

```
C:\Program Files\Ecossistema\
├── ecossistema-agente.exe      # PyInstaller — daemon + CLI
├── ecossistema-receiver.exe     # PyInstaller — legado (opcional)
├── config.example.json          # modelo de configuração
├── setup-windows.ps1            # setup do OpenSSH (manual)
├── start-agente.vbs             # atalho VBS (fallback)
├── README.md
├── PLANO.md
├── INSTALLER.md
├── android/
│   └── ... (projeto APK completo)
```

### 10.2 Registry

```
HKLM\Software\Ecossistema\InstallPath  → "C:\Program Files\Ecossistema"
HKCU\Software\Microsoft\Windows\CurrentVersion\Run\EcossistemaAgente
  → "C:\Program Files\Ecossistema\ecossistema-agente.exe --daemon"
```

### 10.3 Atalhos

```
Menu Iniciar / Ecossistema Híbrido /
├── Agente Ecossistema (.lnk)    → ecossistema-agente.exe --daemon
├── Desinstalar Ecossistema      → msiexec /x {ProductCode}
```

### 10.4 Ícones

Um ícone `.ico` com resoluções 16×16 a 256×256 usado para:
- O executável `ecossistema-agente.exe` (incorporado pelo PyInstaller)
- Atalhos no Menu Iniciar
- Entrada em Add/Remove Programs

---

## 11. Manutenção e Build Automatizado

### 11.1 Script único de build

O `installer/build-msi.ps1` (seção 7.4) é o entry point. O fluxo completo é:

```powershell
# 1. Instalar ferramentas (uma vez)
pip install pyinstaller
dotnet tool install --global wix

# 2. Build
cd ecosistema\installer
.\build-msi.ps1 -Version "1.0.0" -Config "x64"
```

### 11.2 Integração contínua (CI/CD)

Exemplo de pipeline GitHub Actions:

```yaml
name: Build MSI

on:
  push:
    tags: 'v*'

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install PyInstaller
        run: pip install pyinstaller

      - name: Install WiX
        run: dotnet tool install --global wix

      - name: Build MSI
        run: installer\build-msi.ps1 -Version "$env:GITHUB_REF_NAME"

      - name: Upload MSI
        uses: actions/upload-artifact@v4
        with:
          name: Ecossistema-Installer
          path: installer/dist/*.msi
```

### 11.3 Versionamento

O número de versão segue `MAJOR.MINOR.PATCH` conforme a semântica do projeto:

- **MAJOR:** mudanças incompatíveis no protocolo de handoff
- **MINOR:** novas funcionalidades (novos handlers, novo app Android)
- **PATCH:** correções de bugs, melhorias no instalador

O `UpgradeCode` nunca muda. O `ProductCode` é auto-gerado pelo WiX a cada build.

---

## 12. Apêndice

### 12.1 Restrição fundamental: sem Python no PC alvo

O instalador **não pode depender de Python instalado** no PC de destino. Isso
elimina automaticamente abordagens que exigem runtime Python (como executar
`agente.py` diretamente, `setuptools bdist_msi`, ou `cx_Freeze` sem `--onefile`).
**Toda alternativa abaixo precisa produzir um executável standalone (.exe
autocontido) ou ser descartada.**

### 12.2 Alternativas de empacotamento do Python (substituem PyInstaller)

| Ferramenta | Output | Tamanho típico | Funciona sem Python |
|---|---|---|---|
| **PyInstaller** (recomendado) | .exe | ~30 MB | Sim |
| **Nuitka** | .exe (C compilado) | ~15 MB | Sim |
| **cx_Freeze** (com `--onefile`) | .exe | ~35 MB | Sim |
| **Py2Exe** | .exe | ~25 MB | Sim (legado, Python ≤ 3.10) |

Nuitka é uma alternativa viável: compila Python para C nativo, resultando em
executável menor e mais difícil de reverter. Porém, o build é mais lento e a
compatibilidade com bibliotecas dinâmicas (`ctypes`, `socket`) precisa de
testes extras.

### 12.3 Alternativas de instalador (substituem WiX)

> Todas abaixo **empacotam o .exe standalone gerado pelo PyInstaller** (ou
> similar). Nenhuma exige Python no PC alvo.

| Ferramenta | Output | Curva | MSI puro | Grátis | Adequada para |
|---|---|---|---|---|---|
| **Inno Setup** | .exe | Baixa | Não | Sim | Instalador simples sem exigência de MSI |
| **WiX v4** (recomendado) | .msi | Alta | Sim | Sim | Distribuição enterprise, SCCM, Intune, GPO |
| **Advanced Installer Free** | .msi | Baixa | Sim | Free limitada | GUI visual, projetos pequenos |
| **NSIS** | .exe | Média | Não | Sim | Instalador leve e scriptável |
| **Squirrel.Windows** | .exe | Média | Não | Sim | Auto-update (.NET, usado pelo Slack/Spotify) |

### 12.4 Matriz de decisão

```
Precisa de MSI estrito? (SCCM/Intune/GPO)
├── Sim → Precisa de GUI visual?
│   ├── Sim → Advanced Installer (Free até 50 componentes)
│   └── Não → WiX v4 (recomendado — este plano)
└── Não → Inno Setup (mais simples, entrega o mesmo resultado)
```

> **Recomendação final:** PyInstaller (`--onefile`) para empacotar o Python +
> WiX v4 para gerar o MSI. É a combinação mais robusta, gratuita e sem
> dependências de runtime. Se MSI não for estritamente exigido, troque WiX
> por Inno Setup e reduza o tempo de desenvolvimento.
