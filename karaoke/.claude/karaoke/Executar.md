# ▶️ Como Executar o Karaoke AI Premium

Guia operacional para subir o servidor, descobrir o IP de rede, rodar os testes e
diagnosticar os problemas mais comuns de inicialização. Vale tanto para Windows
(ambiente principal de desenvolvimento) quanto para Linux/macOS.

> [!IMPORTANT]
> Todos os comandos pressupõem que você está **dentro da pasta `karaoke/`** e que a
> `venv` já foi criada. Caso ainda não tenha o ambiente, siga a seção
> _Instalação Passo a Passo_ do [README.md](../../README.md).

---

## 1. Ativar o Ambiente Virtual

| Sistema | Comando |
| :--- | :--- |
| Windows PowerShell | `cd karaoke; .\venv\Scripts\Activate.ps1` |
| Windows CMD | `cd karaoke && .\venv\Scripts\activate.bat` |
| Linux / macOS | `cd karaoke && source venv/bin/activate` |

Confirme que a `venv` está ativa: o prompt deve exibir o prefixo `(venv)`. Sempre
use o Python **da venv** (`.\venv\Scripts\python.exe` no Windows ou
`venv/bin/python` no Linux) — usar o Python global é a causa nº 1 de
`ModuleNotFoundError`.

---

## 2. Subir o Servidor

O servidor é um app FastAPI servido por Uvicorn. Ele expõe o frontend estático,
as rotas REST e o WebSocket da sala na **porta 8000**.

### Windows (HTTPS na rede local — comando completo)

O comando abaixo, em uma linha, executa três passos encadeados:
1. **Libera a porta 8000**, encerrando qualquer processo que a esteja ocupando.
2. **Ativa a `venv`**.
3. **Inicia o Uvicorn** em HTTPS no IP da máquina na rede local, com `--reload`.

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; .\venv\Scripts\Activate.ps1; uvicorn server.main:app --host 192.168.15.6 --port 8000 --reload --ssl-keyfile "server/key.pem" --ssl-certfile "server/cert.pem"
```

> Troque `192.168.15.6` pelo IP real da sua máquina na rede Wi-Fi (veja a seção 3).
> O HTTPS é **obrigatório** para celulares: a API `getUserMedia` (microfone) só é
> liberada em contexto seguro. Os arquivos `server/key.pem` e `server/cert.pem`
> precisam existir; gere-os com `mkcert` ou OpenSSL caso ainda não tenha.

### Linux / macOS (HTTPS na rede local)

```bash
# Libera a porta 8000 (se ocupada) e sobe o servidor
fuser -k 8000/tcp 2>/dev/null
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload \
  --ssl-keyfile server/key.pem --ssl-certfile server/cert.pem
```

### Modo HTTP puro (túnel / Cloudflare)

Para rodar sem certificados locais — útil ao expor via Cloudflare Tunnel, que já
provê HTTPS na borda — defina a variável `KARAOKE_HTTP` e omita os flags de SSL:

```bash
# Linux / macOS
KARAOKE_HTTP=1 uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```
```powershell
# Windows PowerShell
$env:KARAOKE_HTTP="1"; uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

Depois de subir, acesse `https://<IP>:8000` no display (TV) e leia o QR Code com o
celular para pareá-lo como microfone.

---

## 3. Descobrir o IP de Rede

O `--host` precisa ser o IP da máquina **na rede Wi-Fi local** (não `127.0.0.1`),
para que os celulares na mesma rede consigam alcançá-lo.

| Sistema | Comando |
| :--- | :--- |
| Windows | `ipconfig` → campo _Endereço IPv4_ do adaptador Wi-Fi |
| Linux | `hostname -I` ou `ip addr show` |
| macOS | `ipconfig getifaddr en0` |

O próprio servidor também expõe o IP detectado em `GET /api/get-ip` após subir.

---

## 4. Executar os Testes

A suíte usa `unittest` e cobre testes unitários (`tests/unit/`) e de fluxo/
integração (`tests/flow/`).

```powershell
# Windows
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```
```bash
# Linux / macOS
venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

Para rodar um único arquivo de teste:
```bash
venv/bin/python -m unittest tests.unit.test_score_engine
```

---

## 5. Diagnóstico Rápido (Troubleshooting)

| Sintoma | Causa provável | Solução |
| :--- | :--- | :--- |
| Microfone do celular não ativa | Servidor em HTTP sem túnel (sem contexto seguro) | Rode em HTTPS com `key.pem`/`cert.pem` ou via Cloudflare Tunnel |
| `ModuleNotFoundError` ao rodar testes | Python global em vez do da `venv` | Use `.\venv\Scripts\python.exe` / `venv/bin/python` |
| Status da GPU preso em `busy` | Reinstalação rodando em paralelo travou o lock | Botão "Destravar GPU" na fila, ou reinicie o servidor |
| Porta 8000 ocupada | Instância anterior não encerrada | O comando Windows acima já libera; no Linux use `fuser -k 8000/tcp` |
| Whisper alucina em silêncio | Trechos silenciosos longos | Gate RMS em `stt_engine.py` rejeita energia < `0.0018` |

Para problemas de alinhamento de letras (timestamps comprimidos, palavras fora de
tempo), consulte o playbook em
[onboarding/PROJECT_GUIDE.md](onboarding/PROJECT_GUIDE.md) e o guia de tuning na
pasta `docs/guides/`.
