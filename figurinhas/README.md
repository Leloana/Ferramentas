# Figurinhas

Cole o link de um vídeo (TikTok, X, YouTube, Instagram... tudo que o `yt-dlp` baixa) e gere uma figurinha de WhatsApp: `.webp` 512x512, animada (até 10 s, ≤ 500 KB) ou imagem parada (≤ 100 KB).

## Rodar

```powershell
cd figurinhas
python -m venv venv; .\venv\Scripts\python.exe -m pip install -r requirements.txt   # só na 1ª vez
.\venv\Scripts\python.exe run.py          # http://127.0.0.1:8020
.\venv\Scripts\python.exe run.py --lan    # libera para o celular na mesma rede
```

Precisa do `ffmpeg` no PATH. O `curl-cffi` (vem no requirements) é o que faz o TikTok funcionar. Se um site parar de baixar, atualize: `pip install -U "yt-dlp[default,curl-cffi]"`.

## Enquadramento

- **Cortar no quadrado**: corta o centro.
- **Escolher área**: um quadrado em cima do vídeo que você arrasta; zoom pelo slider ou pelo canto verde.
- **Vídeo inteiro**: encaixa tudo, com fundo transparente.

## Como cabe no limite do WhatsApp

O tamanho depende quase só de fps × duração. O servidor tenta qualidade 60 a 15 fps; se passar, baixa a qualidade, depois o fps (até 10) e, por último, encurta o trecho (a tela avisa).

## Mandar para o WhatsApp

- WhatsApp Web/Desktop: arraste o `.webp` para a conversa.
- Celular: botão "Compartilhar" → WhatsApp.

Downloads ficam em `work/` e são apagados após 2 h.
