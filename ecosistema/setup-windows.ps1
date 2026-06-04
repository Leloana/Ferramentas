<#
  setup-windows.ps1  --  Setup do lado PC (Windows) do Ecossistema Handoff.

  O que faz (precisa rodar como ADMINISTRADOR):
    1. Instala o OpenSSH Server (Add-WindowsCapability).
    2. Habilita e inicia o servico sshd (startup automatico).
    3. Cria regra de firewall para a porta 22 (TCP).
    4. Autoriza a chave publica do celular (conta admin -> administrators_authorized_keys).
    5. Imprime os dados de conexao para configurar o Termux.

  Uso:
    powershell -ExecutionPolicy Bypass -File setup-windows.ps1 -PhonePubKey "ssh-ed25519 AAAA... termux"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$PhonePubKey
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
        ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) { throw "Este script precisa ser executado como Administrador." }
}

Assert-Admin

function Ensure-SshdService {
    if (Get-Service sshd -ErrorAction SilentlyContinue) {
        Write-Host "    Servico sshd ja registrado." -ForegroundColor Green
        return
    }
    Write-Host "    Servico sshd ausente -> reinstalando capability..." -ForegroundColor Yellow
    $name = (Get-WindowsCapability -Online -Name "OpenSSH.Server*").Name
    try { Remove-WindowsCapability -Online -Name $name -ErrorAction Stop | Out-Null } catch {}
    Add-WindowsCapability -Online -Name $name | Out-Null
    if (Get-Service sshd -ErrorAction SilentlyContinue) {
        Write-Host "    Servico sshd registrado via capability." -ForegroundColor Green
        return
    }
    # Fallback: registra o servico manualmente e gera host keys.
    Write-Host "    Registrando sshd manualmente (fallback)..." -ForegroundColor Yellow
    $ossh = Join-Path $env:WINDIR "System32\OpenSSH"
    $sshDataDir = Join-Path $env:ProgramData "ssh"
    if (-not (Test-Path $sshDataDir)) { New-Item -ItemType Directory -Path $sshDataDir | Out-Null }
    & (Join-Path $ossh "ssh-keygen.exe") -A | Out-Null
    & sc.exe create sshd binPath= "$ossh\sshd.exe" start= auto DisplayName= "OpenSSH SSH Server" obj= LocalSystem | Out-Null
    & sc.exe description sshd "OpenSSH SSH Server" | Out-Null
    if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
        throw "Nao foi possivel registrar o servico sshd. Pode exigir reinicializacao do Windows."
    }
    Write-Host "    Servico sshd registrado manualmente." -ForegroundColor Green
}

Write-Host "==> Instalando OpenSSH Server..." -ForegroundColor Cyan
$cap = Get-WindowsCapability -Online -Name "OpenSSH.Server*"
if ($cap.State -ne "Installed") {
    Add-WindowsCapability -Online -Name $cap.Name | Out-Null
    Write-Host "    OpenSSH Server instalado." -ForegroundColor Green
} else {
    Write-Host "    OpenSSH Server (capability) ja estava instalado." -ForegroundColor Green
}

Write-Host "==> Configurando servico sshd (auto-start)..." -ForegroundColor Cyan
Ensure-SshdService
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
# ssh-agent tambem util para o lado cliente, deixa habilitado.
Set-Service -Name ssh-agent -StartupType Automatic -ErrorAction SilentlyContinue

Write-Host "==> Regra de firewall (porta 22 TCP, todos os perfis)..." -ForegroundColor Cyan
# Nome proprio (evita colidir com a regra padrao do OpenSSH, que e so 'Private').
# Recria para garantir Profile=Any (cobre redes Publicas tambem).
Remove-NetFirewallRule -Name "Handoff-SSH-In-TCP" -ErrorAction SilentlyContinue
New-NetFirewallRule -Name "Handoff-SSH-In-TCP" -DisplayName "Handoff SSH (sshd 22)" `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -Profile Any | Out-Null
Write-Host "    Regra de porta 22 (Any) criada/atualizada." -ForegroundColor Green

# Porta de pareamento por QR (proposta B): o celular conecta no PC em 8766 para
# entregar a chave publica. Sem esta regra o pareamento pela rede expira (o
# Windows bloqueia inbound por padrao). So a janela de --pair usa a porta.
Remove-NetFirewallRule -Name "Handoff-Pair-In-TCP" -ErrorAction SilentlyContinue
New-NetFirewallRule -Name "Handoff-Pair-In-TCP" -DisplayName "Handoff Pareamento (QR 8766)" `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 8766 -Profile Any | Out-Null
Write-Host "    Regra de porta 8766 (pareamento, Any) criada/atualizada." -ForegroundColor Green

Write-Host "==> Autorizando chave publica do celular..." -ForegroundColor Cyan
# Conta admin: o sshd_config padrao do Windows aponta para administrators_authorized_keys.
$adminKeys = Join-Path $env:ProgramData "ssh\administrators_authorized_keys"
# Se uma execucao anterior travou a ACL, retoma posse/acesso antes de ler.
if (Test-Path $adminKeys) {
    & takeown /F $adminKeys /A 2>&1 | Out-Null
    icacls $adminKeys /grant "*S-1-5-32-544:F" "*S-1-5-18:F" 2>&1 | Out-Null
}
$keys = @()
if (Test-Path $adminKeys) {
    try { $keys = @(Get-Content $adminKeys -ErrorAction Stop | Where-Object { $_.Trim() -ne "" }) }
    catch { $keys = @() }
}
if ($keys -notcontains $PhonePubKey) {
    $keys += $PhonePubKey
}
# Grava sem BOM.
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($adminKeys, $keys, $utf8NoBom)
# ACL final restrita via SIDs (independe do idioma: 'Administradores' vs 'Administrators').
#   S-1-5-32-544 = grupo Administradores | S-1-5-18 = SYSTEM
icacls $adminKeys /inheritance:r | Out-Null
icacls $adminKeys /setowner "*S-1-5-32-544" | Out-Null
icacls $adminKeys /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null
Write-Host "    Chave autorizada em $adminKeys (ACL via SID)" -ForegroundColor Green

# Garante que o shell padrao seja o PowerShell? Nao -- mantem cmd.exe (padrao), simples e estavel.

Restart-Service sshd
Write-Host ""
Write-Host "============================================" -ForegroundColor Yellow
Write-Host "  Setup do PC concluido!" -ForegroundColor Yellow
Write-Host "============================================" -ForegroundColor Yellow
$ip = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -like "192.168.*" -and $_.InterfaceAlias -notlike "*vEthernet*" } |
    Select-Object -First 1).IPAddress
Write-Host "  Usuario do PC : $env:USERNAME"
Write-Host "  IP do PC (LAN): $ip"
Write-Host "  Porta SSH     : 22"
Write-Host "  receiver.py   : $(Join-Path $PSScriptRoot 'receiver.py')"
Write-Host ""
