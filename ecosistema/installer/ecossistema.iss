; ============================================================================
;  Ecossistema Híbrido — instalador (Inno Setup 6)
;
;  Empacota o agente standalone (PyInstaller, pasta dist\ecossistema-agente\)
;  num instalador por-usuário (sem admin/UAC):
;    - instala em %LOCALAPPDATA%\Programs\Ecossistema
;    - auto-start no login via HKCU\...\Run  ("...\ecossistema-agente.exe" --daemon)
;    - cria config.json em %APPDATA%\Ecossistema (só se não existir)
;    - atalhos no Menu Iniciar + entrada de desinstalação
;
;  Compilar:  ISCC.exe ecossistema.iss     (gera dist\Ecossistema-Setup-1.0.0.exe)
;  Pré-requisito: rodar antes o PyInstaller (build-exe) gerando dist\ecossistema-agente\.
; ============================================================================

#define AppName "Ecossistema Híbrido"
#define AppVersion "1.0.0"
#define AgentExe "ecossistema-agente.exe"

[Setup]
AppId={{6F2A7C19-4B3D-4E5A-9C8B-1D2E3F4A5B6C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Ecossistema
DefaultDirName={localappdata}\Programs\Ecossistema
DefaultGroupName=Ecossistema Híbrido
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Ecossistema-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AgentExe}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
; Agente standalone (pasta onedir inteira: exe + _internal\).
Source: "dist\ecossistema-agente\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Recursos auxiliares.
Source: "..\setup-windows.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
; config.json do usuário em %APPDATA% — só na primeira vez (preserva edições).
Source: "..\config.example.json"; DestDir: "{userappdata}\Ecossistema"; DestName: "config.json"; Flags: onlyifdoesntexist uninsneveruninstall

[Dirs]
Name: "{userappdata}\Ecossistema"

[Registry]
; Auto-start do daemon no login do usuário.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "EcossistemaAgente"; ValueData: """{app}\{#AgentExe}"" --daemon"; Flags: uninsdeletevalue
; Caminho de instalação (o app Android pode ler via: reg query HKCU\Software\Ecossistema /v InstallPath).
Root: HKCU; Subkey: "Software\Ecossistema"; ValueType: string; \
  ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Icons]
; Painel grafico (HOSPEDA o daemon; assume a porta se o daemon headless ja roda).
Name: "{group}\Painel Ecossistema"; Filename: "{app}\{#AgentExe}"; Parameters: "--panel"
Name: "{autoprograms}\Painel Ecossistema"; Filename: "{app}\{#AgentExe}"; Parameters: "--panel"
Name: "{group}\Agente Ecossistema (daemon headless)"; Filename: "{app}\{#AgentExe}"; Parameters: "--daemon"
Name: "{group}\Pasta de instalação"; Filename: "{app}"
Name: "{group}\Configurar SSH (Admin) — setup-windows.ps1"; Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\setup-windows.ps1"""
Name: "{group}\Desinstalar Ecossistema"; Filename: "{uninstallexe}"

[Run]
; Sobe o agente logo após instalar (oculto: o exe esconde a própria janela em --daemon).
Filename: "{app}\{#AgentExe}"; Parameters: "--daemon"; \
  Description: "Iniciar o agente (daemon headless) agora"; Flags: nowait postinstall skipifsilent
; Ou abrir o painel grafico (assume a porta do daemon headless automaticamente).
Filename: "{app}\{#AgentExe}"; Parameters: "--panel"; \
  Description: "Abrir o painel agora"; Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im {#AgentExe} /f"; Flags: runhidden; RunOnceId: "KillAgente"

[Code]
// Antes de instalar (upgrade), encerra um daemon do exe que esteja rodando
// para liberar os arquivos.
function InitializeSetup(): Boolean;
var ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/im {#AgentExe} /f', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
