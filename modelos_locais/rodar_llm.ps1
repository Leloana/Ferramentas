# Sobe o LLM local em http://localhost:8080/v1 (API compatível com OpenAI).
# Padrão: Qwen3.6-35B-A3B (MoE, experts na RAM, ~30-38 tok/s numa 4070).
# -Max: Qwen3.8-27B (denso, mais inteligente, ~6-10 tok/s porque parte fica na CPU).
#
# Ajuste de VRAM:
#   -CpuMoe (só no 35B-A3B): camadas cujos experts vão pra RAM. Menor = mais rápido e mais VRAM.
#   -Camadas (só no 27B): camadas na GPU. Maior = mais rápido e mais VRAM.
# Olhe o nvidia-smi com o modelo carregado e mire em ~11 GB usados.

param(
    [switch]$Max,
    [string]$Destino = 'D:\IA',
    [int]$Contexto = 65536,
    [int]$CpuMoe = 30,
    [int]$Camadas = 36,
    [int]$Porta = 8080
)

$server = Join-Path $Destino 'llama.cpp\llama-server.exe'
if (-not (Test-Path $server)) { throw "llama-server não encontrado em $server. Rode .\baixar.ps1 -Areas texto" }

$comum = @(
    '--host', '0.0.0.0', '--port', $Porta,
    '-c', $Contexto,
    '-fa', 'on',
    '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
    '--jinja',
    # amostragem recomendada pela Qwen pra código
    '--temp', '0.6', '--top-p', '0.95', '--top-k', '20', '--min-p', '0'
)

if ($Max) {
    $modelo = Join-Path $Destino 'llm\Qwen3.8-27B-UD-Q4_K_XL.gguf'
    $gpu = @('-ngl', $Camadas)
} else {
    $modelo = Join-Path $Destino 'llm\Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf'
    $gpu = @('-ngl', '99', '--n-cpu-moe', $CpuMoe)
}
if (-not (Test-Path $modelo)) { throw "Modelo não encontrado: $modelo" }

Write-Host "Subindo $(Split-Path $modelo -Leaf) em http://localhost:$Porta/v1" -ForegroundColor Cyan
& $server -m $modelo --alias local @gpu @comum
