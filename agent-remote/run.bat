@echo off
title Agent-Remote [Windows Native]
cd /d "%~dp0"

echo =========================================================
echo   🌐  AGENT-REMOTE — CONTROLE WEB REMOTO [WINDOWS]
echo =========================================================
echo.

:: 1. Verifica se o Python está disponível
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO CRITICO] O Python nao foi encontrado no PATH do Windows!
    echo.
    echo 1. Baixe o instalador do Python em https://python.org
    echo 2. IMPORTANTE: Durante a instalacao, marque a caixa:
    echo    "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)

:: 2. Prepara o ambiente virtual venv
if not exist "venv\Scripts\python.exe" (
    echo [agent-remote] Criando ambiente virtual venv...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERRO] Falha ao criar ambiente virtual com 'python -m venv venv'.
        pause
        exit /b 1
    )
    echo [agent-remote] Instalando dependencias (FastAPI, pywinpty, etc)...
    call venv\Scripts\activate.bat
    python -m pip install --upgrade pip --quiet
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: 3. Garante que pywinpty está instalado para o ConPTY (terminal interativo)
python -c "import winpty" >nul 2>&1
if %errorlevel% neq 0 (
    echo [agent-remote] Instalando ConPTY (pywinpty) para terminal interativo no Windows...
    pip install "pywinpty>=2.0.0"
)

:: 4. Executa o servidor principal
echo.
echo [agent-remote] Iniciando servidor e tunel Cloudflare...
python run.py

if %errorlevel% neq 0 (
    echo.
    echo [agent-remote] Servidor finalizado com codigo de erro %errorlevel%.
    pause
)
