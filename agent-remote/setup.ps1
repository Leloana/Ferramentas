$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (-not (Test-Path "venv")) {
    Write-Host "[agent-remote] Criando ambiente virtual venv..." -ForegroundColor Cyan
    python -m venv venv
}

.\venv\Scripts\Activate.ps1
Write-Host "[agent-remote] Instalando dependencias..." -ForegroundColor Cyan
pip install -r requirements.txt

Write-Host "`n[agent-remote] Setup concluido com sucesso! Para iniciar, execute: .\run.bat ou python run.py" -ForegroundColor Green
