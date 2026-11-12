# Baixa os modelos escolhidos no README pro PC da RTX 4070.
# Uso: .\baixar.ps1 [-Areas texto,imagem,video,musica,tts,stt,texto-max] [-Destino D:\IA] [-ComfyModels <pasta models do ComfyUI>]
# Pula o que já existe; pode rodar de novo depois de uma queda.

param(
    [string[]]$Areas = @('texto', 'imagem', 'video', 'musica', 'tts', 'stt'),
    [string]$Destino = 'D:\IA',
    [string]$ComfyModels = "$env:USERPROFILE\Documents\ComfyUI\models"
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Destino | Out-Null

function Garantir-Hf {
    if (Get-Command hf -ErrorAction SilentlyContinue) { return }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    }
    uv tool install "huggingface_hub[cli,hf_xet]"
}

# hf download <repo> <arquivos...> para <pasta>, mantendo a estrutura de subpastas do repo
function Baixar([string]$Repo, [string[]]$Arquivos, [string]$Pasta) {
    New-Item -ItemType Directory -Force -Path $Pasta | Out-Null
    Write-Host "`n>> $Repo -> $Pasta" -ForegroundColor Cyan
    hf download $Repo @Arquivos --local-dir $Pasta
}

# Copia um arquivo baixado pra subpasta certa do ComfyUI (hardlink quando dá, pra não duplicar disco)
function Pro-Comfy([string]$Origem, [string]$Sub) {
    $dir = Join-Path $ComfyModels $Sub
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $alvo = Join-Path $dir (Split-Path $Origem -Leaf)
    if (Test-Path $alvo) { return }
    try { New-Item -ItemType HardLink -Path $alvo -Target $Origem | Out-Null }
    catch { Copy-Item $Origem $alvo }
    Write-Host "   comfy/$Sub/$(Split-Path $Origem -Leaf)"
}

function Garantir-LlamaCpp {
    $dir = Join-Path $Destino 'llama.cpp'
    if (Test-Path (Join-Path $dir 'llama-server.exe')) { return }
    $rel = (Invoke-RestMethod 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=5') |
        Where-Object { $_.tag_name -like 'b*' } | Select-Object -First 1
    $zips = $rel.assets | Where-Object { $_.name -match 'win-cuda-12\.4-x64\.zip$' }
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    foreach ($z in $zips) {
        $tmp = Join-Path $env:TEMP $z.name
        Write-Host ">> llama.cpp $($rel.tag_name): $($z.name)"
        Invoke-WebRequest $z.browser_download_url -OutFile $tmp
        Expand-Archive $tmp -DestinationPath $dir -Force
        Remove-Item $tmp
    }
}

Garantir-Hf

if ($Areas -contains 'texto') {
    Garantir-LlamaCpp
    Baixar 'unsloth/Qwen3.6-35B-A3B-GGUF' @('Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf') "$Destino\llm"
}

if ($Areas -contains 'texto-max') {
    Garantir-LlamaCpp
    Baixar 'unsloth/Qwen3.8-27B-GGUF' @('Qwen3.8-27B-UD-Q4_K_XL.gguf') "$Destino\llm"
}

if ($Areas -contains 'imagem') {
    $p = "$Destino\imagem"
    Baixar 'Comfy-Org/Qwen-Image-2.1' @(
        'diffusion_models/qwen_image_2.1_int8_convrot.safetensors',
        'text_encoders/qwen3vl_8b_int8_convrot.safetensors',
        'vae/qwen_image_2.1_vae_bf16.safetensors'
    ) $p
    Pro-Comfy "$p\diffusion_models\qwen_image_2.1_int8_convrot.safetensors" 'diffusion_models'
    Pro-Comfy "$p\text_encoders\qwen3vl_8b_int8_convrot.safetensors" 'text_encoders'
    Pro-Comfy "$p\vae\qwen_image_2.1_vae_bf16.safetensors" 'vae'
}

if ($Areas -contains 'video') {
    $p = "$Destino\video"
    Baixar 'realrebelai/LTX-2.5_GGUFs' @('LTX-2.5-Distilled-Q4_K_S.gguf', 'LTX 2.5 GGUF (WORKFLOW).json') $p
    Baixar 'Lightricks/LTX-2.5' @(
        'text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors',
        'vae/ltx-2.5-video-vae-bf16.safetensors',
        'vae/ltx-2.5-audio-vae-bf16.safetensors',
        'latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors'
    ) $p
    Pro-Comfy "$p\LTX-2.5-Distilled-Q4_K_S.gguf" 'unet'
    Pro-Comfy "$p\text_encoders\gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors" 'text_encoders'
    Pro-Comfy "$p\vae\ltx-2.5-video-vae-bf16.safetensors" 'vae'
    Pro-Comfy "$p\vae\ltx-2.5-audio-vae-bf16.safetensors" 'vae'
    Pro-Comfy "$p\latent_upscale_models\ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors" 'latent_upscale_models'
    Write-Host "   workflow: $p\LTX 2.5 GGUF (WORKFLOW).json (arrastar pro ComfyUI; precisa do nó ComfyUI-GGUF)"
}

if ($Areas -contains 'musica') {
    $repo = "$Destino\ACE-Step-1.5"
    if (-not (Test-Path $repo)) { git clone https://github.com/ace-step/ACE-Step-1.5 $repo }
    $ck = "$repo\checkpoints"
    # pacote base (VAE, embedding, LM 1.7B) + DiT XL Turbo
    Baixar 'ACE-Step/Ace-Step1.5' @() $ck
    Baixar 'ACE-Step/acestep-v15-xl-turbo' @() "$ck\acestep-v15-xl-turbo"
    $envFile = "$repo\.env"
    if (-not (Test-Path $envFile)) {
        "ACESTEP_CONFIG_PATH=acestep-v15-xl-turbo`nACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-1.7B" |
            Set-Content -Encoding ascii $envFile
    }
}

if ($Areas -contains 'tts') {
    Baixar 'Benjonson/s2-pro-fp8' @() "$Destino\tts\s2-pro-fp8"
}

if ($Areas -contains 'stt') {
    Baixar 'Systran/faster-whisper-large-v3' @() "$Destino\stt\faster-whisper-large-v3"
}

Write-Host "`nPronto. Modelos em $Destino" -ForegroundColor Green
