$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "  🌐  AGENT-REMOTE — SETUP WINDOWS NATIVO" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan

if (-not (Test-Path "venv\Scripts\python.exe")) {
    Write-Host "[agent-remote] Criando ambiente virtual venv..." -ForegroundColor Yellow
    python -m venv venv
}

Write-Host "[agent-remote] Ativando venv e instalando dependencias..." -ForegroundColor Yellow
& ".\venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
& ".\venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\venv\Scripts\python.exe" -m pip install "pywinpty>=2.0.0"

Write-Host "`n[agent-remote] Setup concluido com sucesso no Windows!" -ForegroundColor Green
Write-Host "Para iniciar, execute: .\run.bat ou python run.py" -ForegroundColor Green
