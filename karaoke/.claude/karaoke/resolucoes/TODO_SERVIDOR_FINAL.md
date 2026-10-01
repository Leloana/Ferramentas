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
- [ ] **Versão do áudio × letra, nota em ordem e RoFormer** (branch `feat/karaoke-versoes-robustas`) —
      roteiro pronto abaixo, em "Testes prontos para a máquina com GPU".
- [ ] **Volume** — ouvir antes/depois da normalização (limitador em faixas com muito pico); reinstalar as
      músicas antigas para nivelar.
- [ ] **Afinação** — conferir se "tom X%" separa cantar afinado de desafinado antes de pensar em pôr na nota
      (`MIC_RMS_GATE`, harmonias no stem, vazamento da TV).
- [ ] **Gravações novas** (formato 2, com as duas passadas do Whisper) → virar fixture com gabarito →
      calibrar `PROMPT_TRUST_MIN_PROB`, VAD, tolerância de tempo.
- [ ] **Tela acesa** no celular-microfone durante uma música inteira (Android e iPhone).

## Testes prontos para a máquina com GPU (2026-10-01)

Feitos e medidos em CPU. Falta GPU e música real. `tools/validar_gpu.py` roda cada um com um comando, do
venv do servidor, de dentro de `karaoke/`, **com o servidor parado** (o script carrega o próprio Whisper e
o MMS_FA na GPU). Relatórios JSON e os áudios para ouvir saem em `validacao_gpu/` (fora do git).

```powershell
git fetch; git switch feat/karaoke-versoes-robustas
python -m pytest -q tests/unit tests/flow                    # 1. suíte (261 testes em 2026-10-01)
pip install audio-separator==0.47.0                           # 2. opcional: liga o RoFormer
python tools/validar_gpu.py ambiente                          # 3. GPU, versões, separador escolhido
python tools/validar_gpu.py baixar-modelo                     # 4. ~600 MB, fora do lock da GPU
python tools/validar_gpu.py separacao server/songs/<slug>/original.mp3 --com-whisper   # 5.
python tools/validar_gpu.py versoes                           # 6. Holiday em 6 versões simuladas
python tools/validar_gpu.py musica server/songs/<slug>        # 7. música real (repetir em 3–5)
```

- [ ] **1. Suíte** — tudo verde com o torch cu124 (aqui foi o torch de CPU).
- [ ] **3. Ambiente** — `fora_do_requirements` vazio depois do `pip install audio-separator`. Se ele subiu o
      numpy ou o onnxruntime, rodar a suíte de novo e testar o VAD do Whisper ao vivo (usa o onnxruntime).
      Se quebrar: `pip install -r requirements.txt` volta as versões e `KARAOKE_SEPARATOR=demucs` desliga.
- [ ] **5. Separação** — RoFormer × Demucs na mesma música, com o Whisper carregado como no servidor:
      tempo, pico de VRAM e `validacao_gpu/separacao-*/*-instrumental.wav` para ouvir (voz vazando,
      pratos, reverb). Repetir em 3 músicas de estilos diferentes. VRAM pico + Whisper tem que caber com
      folga: senão `KARAOKE_SEPARATOR=demucs`.
- [ ] **6. Versões simuladas** — esperado (medido em CPU): PRO "agora" 39/39 em `orig`, `intro8` e `slow3`,
      39/42 no `extrachorus`, e o `cutverse` sem as 6 linhas do verso 2. Modo rápido "agora" 39/39 no
      `intro8` (antes 0/39) e 31/33 no `cutverse` (antes 11/33). Anotar o tempo do Whisper do stem: é o
      custo extra de cada reinstall.
- [ ] **7. Música real** — 3–5 músicas cuja versão do YouTube não é a de estúdio (ao vivo, radio edit,
      intro longa). O comando mostra o encaixe, a estrutura, a concordância e o método escolhido, e grava
      `validacao_gpu/<slug>.sync_preview.lrc` sem mexer no `lyrics.lrc`. Abrir no editor de letra e tocar.
      Se o método errar, anotar a concordância e a cobertura: os limiares são `MIN_AGREEMENT` (0,6) e
      `PLAN_MIN_COVERAGE` (0,35) em `server/utils/lrc_sync.py`.
- [ ] **8. Nota em ordem numa partida** — cantar uma música conhecida e conferir que verso certo continua
      perto de 100. Cantar embaralhado de propósito deve cair. Gravar a partida (formato 2) e anotar no
      gabarito o verso 35 de Wolf at the Door (caiu de 89,5 para 72,7 porque o Whisper não ouviu "Tells me all").
- [ ] **9. Reinstall de verdade** — reinstalar pela interface uma das músicas do item 7 no modo rápido e
      uma no PRO. No log: `[LRC FIT]`, `[ESTRUTURA]`, `LRC para este áudio: <método>` e, no PRO,
      `candidato ...: nota`. A 2ª vez da mesma música não deve transcrever de novo (`.structure_words.json`).

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
