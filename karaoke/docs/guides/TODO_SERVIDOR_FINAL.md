# TODO — Servidor final (Cloudflare Tunnel em `karaoke.myall.net.br`)

> Pendente: fazer **na máquina que vai hospedar o karaokê**, não na de desenvolvimento.
> O código já está pronto para o túnel (P0 de 2026-09-29). Falta só a infraestrutura abaixo.

O objetivo é servir o karaokê por HTTPS válido para os celulares, inclusive iPhone. O Safari só libera
o microfone em página segura, e o certificado autoassinado (`server/key.pem`) dá atrito no iOS.

```
Celular/TV ──https/wss──> Cloudflare (TLS + Access) ──túnel──> cloudflared ──http──> uvicorn 127.0.0.1:8000
```

## Checklist

- [ ] **Instalar o `cloudflared`** — `winget install --id Cloudflare.cloudflared` (mesmo passo do
      [guia do agent-remote](../../../agent-remote/GUIA_CLOUDFLARE.md)).
- [ ] **Criar o túnel nomeado** e apontar o subdomínio:
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
- [ ] **Tirar `server/key.pem` e `server/cert.pem` do git.** A chave privada está versionada. Com o
      túnel ela não é mais usada. Quem quiser o modo LAN gera um par local, fora do repo.

## Validar no servidor (GPU + celulares de verdade)

O que foi feito em 2026-09-30 sem GPU nem áudio real e ainda precisa ser conferido. Roteiro passo a passo
(com os cenários de gravação) em [PLANO_SERVIDOR.md](PLANO_SERVIDOR.md). Detalhes de cada
item de áudio em [AUDIO_PIPELINE_MELHORIAS.md](AUDIO_PIPELINE_MELHORIAS.md).

- [ ] **Suíte completa** — `python -m pytest -q tests` (inclui `tests/test_escolta_vagalumes.py`, que precisa de CUDA
      e do áudio da música) e `python -m pytest tests/ui` (Playwright, se instalado).
- [ ] **Partida com 2–4 celulares** — nota por verso, duplas/trios, revezar versos ("Vez de…"), carimbo e
      "tom X%", cartão para print no fim (TV e cada celular), "Ouvir".
- [ ] **Queda de rede** — derrubar o Wi-Fi da TV no meio da música: deve voltar sem zerar o placar. Celular que
      cai: registrar o mesmo apelido de novo e voltar a pontuar.
- [ ] **Fila da noite** — pedir música pelo celular, "Próximas" na TV, contagem de 10 s no fim abrindo a próxima.
- [ ] **Mutex de GPU** — adicionar uma música durante a partida: a fase 1 roda junto; ao terminar a partida a
      fase 2 começa e o INICIAR mostra "GPU ocupada" até ela acabar.
- [ ] **Alinhamento PRO** em 5–10 músicas com LRC do LRCLIB: sem estouro de memória, tempo por música,
      `alignment_quality` coerente (as ruins viram "Revisar").
- [ ] **Versão do áudio × letra** — reinstalar 5 músicas de versão diferente da do LRCLIB (ao vivo, edit,
      intro longa) e conferir no log `[LRC FIT]`, `[ESTRUTURA]` e `LRC para este áudio: <método>`. Medir o
      tempo extra do Whisper do stem inteiro (estrutura) no modo rápido.
- [ ] **RoFormer** — `pip install audio-separator==0.47.0` no venv (confere se não troca o numpy/onnxruntime
      do `requirements.txt`), baixar o modelo antes (1ª separação baixa ~600 MB com o lock preso), reinstalar 5
      músicas e ouvir o instrumental × Demucs. VRAM (com o Whisper carregado) e tempo por música.
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
