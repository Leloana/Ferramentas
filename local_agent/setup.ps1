<#
.SYNOPSIS
    Configura o runtime do agente local (PLANO.md secões 4 e 9.1):
    - Define as variáveis de ambiente obrigatórias (flash attention, KV cache Q8_0).
    - Cria o modelo customizado `local-agent` a partir do Modelfile (num_ctx explícito).
    - Instala as dependências Python.

.NOTES
    As variáveis de ambiente do Ollama só têm efeito depois que o app for
    reiniciado. Este script avisa isso no final; não reinicia o app sozinho.
#>

$ErrorActionPreference = "Stop"

Write-Host "== 1/3: variáveis de ambiente (persistentes, escopo usuário) ==" -ForegroundColor Cyan
[Environment]::SetEnvironmentVariable("OLLAMA_FLASH_ATTENTION", "1", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KV_CACHE_TYPE", "q8_0", "User")
$env:OLLAMA_FLASH_ATTENTION = "1"
$env:OLLAMA_KV_CACHE_TYPE = "q8_0"
Write-Host "  OLLAMA_FLASH_ATTENTION=1"
Write-Host "  OLLAMA_KV_CACHE_TYPE=q8_0"

Write-Host "`n== 2/3: modelo customizado 'local-agent' (Modelfile: num_ctx=24576) ==" -ForegroundColor Cyan
$modelfile = Join-Path $PSScriptRoot "Modelfile"
ollama create local-agent -f $modelfile

Write-Host "`n== 3/3: dependências Python ==" -ForegroundColor Cyan
$requirements = Join-Path $PSScriptRoot "requirements.txt"
python -m pip install -r $requirements

Write-Host "`n== Pronto ==" -ForegroundColor Green
Write-Host "IMPORTANTE: reinicie o app do Ollama (bandeja do sistema -> Quit, depois abrir de novo)"
Write-Host "para que OLLAMA_FLASH_ATTENTION e OLLAMA_KV_CACHE_TYPE tenham efeito."
Write-Host "`nDefina LOCAL_AGENT_MODEL=local-agent (ou copie .env.example para .env) para usar"
Write-Host "o modelo customizado em vez do 'qwen3.5:9b-instruct' cru."
