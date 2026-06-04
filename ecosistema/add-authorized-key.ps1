<#
  add-authorized-key.ps1  --  Autoriza UMA chave publica no PC (uso do pareamento).

  Extrai a logica de "anexar chave + ACL restrita" do setup-windows.ps1 para que
  o pareamento por QR (agente.py --pair) possa autorizar a chave gerada no celular
  com UMA elevacao (UAC). Le a chave de um ARQUIVO (evita problemas de aspas) e,
  por padrao, apaga esse arquivo temporario ao terminar.

  Uso (chamado elevado pelo agente):
    powershell -NoProfile -ExecutionPolicy Bypass -File add-authorized-key.ps1 -PubKeyFile C:\Temp\k.pub
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$PubKeyFile,
    [switch]$KeepFile
)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw "Precisa rodar como Administrador." }

if (-not (Test-Path $PubKeyFile)) { throw "Arquivo de chave nao encontrado: $PubKeyFile" }
$PhonePubKey = (Get-Content $PubKeyFile -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($PhonePubKey)) { throw "Chave publica vazia." }

# Conta admin: o sshd_config padrao do Windows usa administrators_authorized_keys.
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
# ACL final restrita via SIDs (independe do idioma):
#   S-1-5-32-544 = Administradores | S-1-5-18 = SYSTEM
icacls $adminKeys /inheritance:r | Out-Null
icacls $adminKeys /setowner "*S-1-5-32-544" | Out-Null
icacls $adminKeys /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null

if (-not $KeepFile) { Remove-Item $PubKeyFile -Force -ErrorAction SilentlyContinue }
Write-Host "Chave autorizada em $adminKeys" -ForegroundColor Green
