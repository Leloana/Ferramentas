<#
.SYNOPSIS
  Gera o instalador do Ecossistema Híbrido (agente standalone + Inno Setup).
.DESCRIPTION
  1. PyInstaller empacota agente.py -> dist\ecossistema-agente\ (onedir, console).
  2. Inno Setup (ISCC) compila ecossistema.iss -> dist\Ecossistema-Setup-<versao>.exe.

  Pré-requisitos: Python + pyinstaller (pip install pyinstaller) e Inno Setup 6.
.EXAMPLE
  .\build.ps1
#>
param(
  [switch]$SkipExe   # pula o PyInstaller (reaproveita o exe já gerado)
)

$ErrorActionPreference = "Stop"
$Here = $PSScriptRoot
$Root = Resolve-Path (Join-Path $Here "..")

if (-not $SkipExe) {
  Write-Host "[1/2] Empacotando agente.py (PyInstaller, standalone)..." -ForegroundColor Cyan
  python -m PyInstaller --onedir --noconfirm --clean --name ecossistema-agente `
    --distpath (Join-Path $Here "dist") `
    --workpath (Join-Path $Here "build") `
    --specpath $Here `
    (Join-Path $Root "agente.py")
  if (-not (Test-Path (Join-Path $Here "dist\ecossistema-agente\ecossistema-agente.exe"))) {
    throw "PyInstaller não gerou o exe."
  }
} else {
  Write-Host "[1/2] (pulado) reaproveitando dist\ecossistema-agente\" -ForegroundColor DarkGray
}

Write-Host "[2/2] Compilando o instalador com Inno Setup (ISCC)..." -ForegroundColor Cyan
$iscc = Get-ChildItem `
  "C:\Program Files (x86)\Inno Setup*\ISCC.exe", `
  "C:\Program Files\Inno Setup*\ISCC.exe", `
  "$env:LOCALAPPDATA\Programs\Inno Setup*\ISCC.exe" -ErrorAction SilentlyContinue |
  Select-Object -First 1
if (-not $iscc) { throw "ISCC.exe (Inno Setup) não encontrado. Instale o Inno Setup 6." }

& $iscc.FullName (Join-Path $Here "ecossistema.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou." }

$out = Get-ChildItem (Join-Path $Here "dist\Ecossistema-Setup-*.exe") -ErrorAction SilentlyContinue |
  Select-Object -Last 1
Write-Host "OK: $($out.FullName)" -ForegroundColor Green
