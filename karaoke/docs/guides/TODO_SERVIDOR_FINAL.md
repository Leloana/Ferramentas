# TODO — Servidor final (Cloudflare Tunnel em `karaoke.myall.net.br`)

> Pendente: fazer **na máquina que vai hospedar o karaokê**, não na de desenvolvimento.
> O código já está pronto para o túnel (P0 de 2026-09-29). Falta só a infraestrutura abaixo.

O objetivo é servir o karaokê por HTTPS válido para os celulares, inclusive iPhone. O Safari só libera
o microfone em página segura, e o certificado autoassinado (`server/key.pem`) dá atrito no iOS.

```
Celular/TV ──https/wss──> Cloudflare (TLS + Access) ──túnel──> cloudflared ──http──> uvicorn 127.0.0.1:8000
```

## 1º teste: rodar `tools/validar_gpu.py` (feito no servidor em 2026-10-01)

`tools/validar_gpu.py` roda cada item com um comando, do venv do servidor, de dentro de `karaoke/`, **com o
servidor parado** (o script carrega o próprio Whisper e o MMS_FA na GPU). Relatórios JSON e os áudios para
ouvir saem em `validacao_gpu/` (fora do git). O código já está no `main`.

```powershell
python -m pytest -q tests                                     # 1. suíte inteira (276 em 2026-10-01)
pip install audio-separator==0.47.0 audioread                 # 2. liga o RoFormer; em seguida, OBRIGATÓRIO:
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 --index-url https://download.pytorch.org/whl/cu124 --extra-index-url https://pypi.org/simple
python tools/validar_gpu.py ambiente                          # 3. GPU, versões, separador escolhido
python tools/validar_gpu.py baixar-modelo                     # 4. ~600 MB, fora do lock da GPU
python tools/validar_gpu.py separacao <audio original> --com-whisper   # 5. as pastas não guardam o original:
                                                              #    baixar do youtube_vocal_url do meta.json com o yt-dlp
python tools/validar_gpu.py versoes                           # 6. Holiday em 6 versões simuladas
python tools/validar_gpu.py musica server/songs/<slug>        # 7. música real
```

O `pip install audio-separator` troca o torch cu124 por um torch 2.14 **de CPU** (o `onnx2torch` puxa o
`torchvision` mais novo) e o `librosa` 1.0 não traz mais o `audioread`, que ele importa. Por isso a 2ª linha.
Depois dela: `pip check` limpo, numpy 2.4.6 e onnxruntime 1.26.0 iguais ao `requirements.txt`.

- [x] **1. Suíte** — 261 de `tests/unit tests/flow` com torch cu124, antes e depois do audio-separator.
      Inteira (`tests`, com o Escolta de Vagalumes na GPU e os 10 de UI com Playwright): 276 verdes.
- [x] **3. Ambiente** — `fora_do_requirements` vazio, `separador_auto` = roformer.
- [x] **5. Separação** — medido. Falta **ouvir** `validacao_gpu/separacao-*/*-instrumental.wav`.

      | música (estilo, duração) | RoFormer | Demucs | VRAM pico (com Whisper) |
      | :--- | ---: | ---: | :--- |
      | Hysteria, Muse (rock, 3:47) | 65 s | 8,6 s | 5,2 GB × 3,6 GB |
      | Construção, Chico (MPB/orquestra, 6:24) | 104 s | 34 s | 5,2 GB × 3,6 GB |
      | Oh No!, Marina (pop, 3:00) | 66 s | 7,3 s | 5,2 GB × 3,6 GB |

      Cabe com folga nos 12 GB (só o Whisper ocupa 2,7 GB). O RoFormer custa ~1 min a mais por música na
      fila. O Whisper não reconhece nenhuma palavra no instrumental de nenhum dos dois: a diferença, se
      houver, é de ouvido (voz de fundo, pratos, reverb). Se não compensar o tempo: `KARAOKE_SEPARATOR=demucs`.
- [x] **6. Versões simuladas** — PRO "agora" 39/39 em `orig`, `intro8` e `slow3`, 38/39 no `cut5fast3`, 39/42
      no `extrachorus` e 30/33 no `cutverse`, como na CPU. Rápido "agora" 39/39 no `intro8` (antes 0/39) e
      30/33 no `cutverse` (CPU deu 31/33). Whisper do stem: 2,4–5,9 s por versão; PRO ~9–12 s.
- [ ] **7. Música real** — rodado nas 57 músicas (`validacao_gpu/musicas.log` e um
      `validacao_gpu/<slug>.sync_preview.lrc` por música; o `lyrics.lrc` não foi mexido). Whisper do stem:
      4–9 s. Método escolhido: `lrc` em 39, `lrc+encaixe` em 10, `estrutura` em 8. Falta **tocar no editor
      de letra** as que mudariam e conferir se a escolha está certa, a começar pelas suspeitas:
      - `hey-pixies`: encaixe de +23,7 s com escala 1,08, concordância 0 e 5 linhas fora, e mesmo assim
        `lrc+encaixe` (32 linhas mudam). A mais provável de estar errada.
      - `dia-clarear-banda-do-mar` (encaixe −8,25 s, concordância 0 → estrutura), `hysteria-muse`
        (concordância 0,05 → estrutura), `flores-astrais-ney-matogrosso` (escala 1,074 → estrutura).
      - `insista-em-mim-ana-frango-eletrico` (+11,45 s) e `take-a-bite-beabadoobee` (+9,45 s): intro longa?
      - `o-vira-ney-matogrosso` e `samurai-djavan`: 48 linhas a mais de 1 s do LRC atual.
      - `dela-ana-frango-eletrico`: 10 linhas fora, 53% das palavras casadas, mas fica no `lrc`.
      Se o método errar, anotar a concordância e a cobertura: os limiares são `MIN_AGREEMENT` (0,6) e
      `PLAN_MIN_COVERAGE` (0,35) em `server/utils/lrc_sync.py`.
- [ ] **8. Nota em ordem numa partida** — cantar uma música conhecida e conferir que verso certo continua
      perto de 100. Cantar embaralhado de propósito deve cair. Gravar a partida (formato 2) e anotar no
      gabarito o verso 35 de Wolf at the Door (caiu de 89,5 para 72,7 porque o Whisper não ouviu "Tells me all").
- [ ] **9. Reinstall de verdade** — reinstalar pela interface uma das músicas do item 7 no modo rápido e
      uma no PRO. No log: `[LRC FIT]`, `[ESTRUTURA]`, `LRC para este áudio: <método>` e, no PRO,
      `candidato ...: nota`. A 2ª vez da mesma música não deve transcrever de novo (`.structure_words.json`).

## Checklist

- [x] **Instalar o `cloudflared`** — `winget install --id Cloudflare.cloudflared` (mesmo passo do
      [guia do agent-remote](../../../agent-remote/GUIA_CLOUDFLARE.md)).
- [x] **Criar o túnel nomeado** (no servidor real é um túnel do painel, por token: só a *Public Hostname* `karaoke.myall.net.br → http://127.0.0.1:8000`; não rodar os comandos abaixo) e apontar o subdomínio:
      ```powershell
      cloudflared tunnel login
      cloudflared tunnel create karaoke
      cloudflared tunnel route dns karaoke karaoke.myall.net.br
      ```
      `%USERPROFILE%\.cloudflared\config.yml`:
      ```yaml
      tunnel: karaoke
      credentials-file: C:\Users\<usuario>\.cloudflared\<ID-DO-TUNEL>.json
      ingress:
        - hostname: karaoke.myall.net.br
          service: http://127.0.0.1:8000
        - service: http_status:404
      ```
      WebSocket passa pelo túnel sem configuração extra. Para subir com o Windows:
      `cloudflared service install`.
- [ ] **Subir o servidor só em localhost, sem SSL** (o TLS fica no Cloudflare):
      ```powershell
      $env:KARAOKE_PUBLIC_URL = "https://karaoke.myall.net.br"
      .\venv\Scripts\Activate.ps1
      uvicorn server.main:app --host 127.0.0.1 --port 8000
      ```
      `KARAOKE_PUBLIC_URL` faz os QR Codes apontarem para o domínio, mesmo com a TV aberta em `localhost`.
- [ ] **Cloudflare Access** (Zero Trust → Access → Applications → Self-hosted) nas rotas que mexem no
      acervo ou ocupam a GPU. Política: só os e-mails da casa.
      - `karaoke.myall.net.br/api/upload-song`
      - `karaoke.myall.net.br/api/delete-song/*`
      - `karaoke.myall.net.br/api/reinstall-song/*`
      - `karaoke.myall.net.br/api/save-lyrics` · `/api/save-meta`
      - `karaoke.myall.net.br/api/queue/*`
      - Rotas novas do redesign (2026-09-30): `/api/youtube-search` (busca via yt-dlp, sem download) e
        `/api/songs/*/cover` (baixa a capa uma vez). Leves, mas usam a rede do servidor: decidir se entram no Access.
      - Na TV, logar uma vez abrindo `https://karaoke.myall.net.br/api/queue/status`. O cookie
        `CF_Authorization` vale para os `fetch` da página depois.
      - **Decidir:** o QR da tela inicial abre `/?open=add-song` no celular, que usa `/api/queue/add`.
        Protegido = o celular também faz login (OTP por e-mail). Público = qualquer um com a URL
        enfileira download na GPU.
- [x] **Cache Rule no Cloudflare** (feito em 2026-09-29). Sem ela o *Browser Cache TTL* da zona (4 h)
      troca o `no-cache` do servidor por `max-age=14400` e o celular fica com JS velho após uma
      atualização. *Bypass cache* **não** resolve (não mexe no TTL do navegador).
      Caching → Cache Rules: expressão `(http.host eq "karaoke.myall.net.br")` · *Eligible for cache* ·
      Edge TTL *Use cache-control header if present, bypass cache if not* · Browser TTL *Respect origin TTL*.
- [x] **Conferir o cache da borda:** `curl -sI https://karaoke.myall.net.br/js/main.js` deve trazer
      `cache-control: no-cache` e `cf-cache-status` diferente de `HIT` (hoje: `REVALIDATED`).
- [ ] **Teste no iPhone:** Safari → QR de pareamento → permitir microfone → cantar um verso inteiro.
      A nota de um verso cantado certinho deve chegar perto de 100 (antes do P0 o teto era 85).
- [x] **Tirar `server/key.pem` e `server/cert.pem` do git** (2026-10-01). Saíram do índice e o `.gitignore`
      cobre `server/*.pem`; os arquivos seguem no disco, então `karaoke -lan` funciona. A chave continua no
      histórico do git: se o modo LAN voltar a ser usado, gerar um par novo.

## Validar no servidor (GPU + celulares de verdade)

O que foi feito em 2026-09-30 sem GPU nem áudio real e ainda precisa ser conferido. Roteiro passo a passo
(com os cenários de gravação) em [PLANO_SERVIDOR.md](PLANO_SERVIDOR.md). Detalhes de cada
item de áudio em [AUDIO_PIPELINE_MELHORIAS.md](AUDIO_PIPELINE_MELHORIAS.md).

- [x] **Suíte completa** — `python -m pytest -q tests`: 276 verdes em 2026-10-01, com CUDA e Playwright
      instalados no venv do servidor (`pip install playwright` + `python -m playwright install chromium`).
- [ ] **Partida com 2–4 celulares** — nota por verso, duplas/trios, revezar versos ("Vez de…"), carimbo e
      "tom X%", cartão para print no fim (TV e cada celular), "Ouvir".
- [ ] **Queda de rede** — derrubar o Wi-Fi da TV no meio da música: deve voltar sem zerar o placar. Celular que
      cai: registrar o mesmo apelido de novo e voltar a pontuar.
- [ ] **Fila da noite** — pedir música pelo celular, "Próximas" na TV, contagem de 10 s no fim abrindo a próxima.
- [ ] **Mutex de GPU** — adicionar uma música durante a partida: a fase 1 roda junto; ao terminar a partida a
      fase 2 começa e o INICIAR mostra "GPU ocupada" até ela acabar.
- [ ] **Alinhamento PRO** em 5–10 músicas com LRC do LRCLIB: sem estouro de memória, tempo por música,
      `alignment_quality` coerente (as ruins viram "Revisar").
- [ ] **Versão do áudio × letra, nota em ordem e RoFormer** (branch `feat/karaoke-versoes-robustas`) —
      roteiro pronto no topo deste arquivo, em "1º teste".
- [ ] **Volume** — ouvir antes/depois da normalização (limitador em faixas com muito pico); reinstalar as
      músicas antigas para nivelar.
- [ ] **Afinação** — conferir se "tom X%" separa cantar afinado de desafinado antes de pensar em pôr na nota
      (`MIC_RMS_GATE`, harmonias no stem, vazamento da TV).
- [ ] **Gravações novas** (formato 2, com as duas passadas do Whisper) → virar fixture com gabarito →
      calibrar `PROMPT_TRUST_MIN_PROB`, VAD, tolerância de tempo.
- [ ] **Tela acesa** no celular-microfone durante uma música inteira (Android e iPhone).

## Variáveis de ambiente

| Variável | Servidor final | Função |
| :--- | :--- | :--- |
| `KARAOKE_PUBLIC_URL` | `https://karaoke.myall.net.br` | URL que vai nos QR Codes |
| `KARAOKE_HTTP` | `1` (só se rodar via `python server/main.py`) | Ignora `key.pem`/`cert.pem` |
| `KARAOKE_HOST` | `127.0.0.1` (só via `python server/main.py`) | Endereço de escuta |
| `KARAOKE_PORT` | `8000` | Porta de escuta |
| `KARAOKE_SEPARATOR` | `auto` (RoFormer se `pip install audio-separator==0.47.0`, senão Demucs) | Separador voz × instrumental |
| `KARAOKE_ROFORMER_MODEL` | `model_bs_roformer_ep_317_sdr_12.9755.ckpt` | Modelo do RoFormer (~600 MB, baixa na 1ª vez) |
| `KARAOKE_DEMUCS_MODEL` | `htdemucs` (testar `htdemucs_ft`) | Modelo do Demucs (fallback do RoFormer) |
| `KARAOKE_MP3_BITRATE` | `320k` | Bitrate dos MP3 |
| `KARAOKE_RECORD` / `KARAOKE_RECORD_DIR` | ligado | Grava as partidas para calibrar a nota |
