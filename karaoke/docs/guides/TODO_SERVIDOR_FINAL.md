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

## Variáveis de ambiente

| Variável | Servidor final | Função |
| :--- | :--- | :--- |
| `KARAOKE_PUBLIC_URL` | `https://karaoke.myall.net.br` | URL que vai nos QR Codes |
| `KARAOKE_HTTP` | `1` (só se rodar via `python server/main.py`) | Ignora `key.pem`/`cert.pem` |
| `KARAOKE_HOST` | `127.0.0.1` (só via `python server/main.py`) | Endereço de escuta |
| `KARAOKE_PORT` | `8000` | Porta de escuta |
