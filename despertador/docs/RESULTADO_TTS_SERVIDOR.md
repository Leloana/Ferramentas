# Resultado do teste de TTS local no servidor

Executado em 10/11/2026, das 22:11 às 22:21 UTC, seguindo `TESTE_TTS_SERVIDOR.md`. Roteiro: `server/conteudo/2026-11-10/roteiro.json` (1.075 caracteres).

## Resultado

| motor | status | voz | carga do modelo (s) | síntese (s) | áudio (s) | RTF | pico RAM (MB) |
|---|---|---|---|---|---|---|---|
| piper | ok | pt_BR-faber-medium | 2.5 | 5.4 | 59.3 | 0.09 | 335 |
| kokoro | **pulado** | pm_alex | | | | | |
| xtts | ok | Damien Black | 47.5 | 211.8 | 92.9 | 2.28 | 4384 |

Condições: 4 threads por motor, `nice 19`, `ionice -c3`, dentro de `systemd-run --user --scope -p MemoryMax=7G -p CPUQuota=400%` (funcionou sem sudo). Um motor por vez.

- **Piper:** cerca de 8 s no total para 1 minuto de áudio. RTF de 0,09 no Xeon, contra 0,06 no i5-13400F.
- **XTTS-v2:** cerca de 4 min e 23 s no total, sendo 47 s para carregar o modelo e 3 min e 32 s de síntese. O pico de RAM foi de 4,4 GB. O áudio ficou 57% mais longo que o do Piper (93 s contra 59 s). Conferi com `silencedetect` que isso não vem de buracos: são 17 pausas entre frases, que somam 9,9 s, e a maior tem 0,63 s. A diferença vem do ritmo de fala mais lento (~11,6 caracteres/s, contra ~18 do Piper). Vale escutar a amostra inteira, porque o XTTS às vezes repete ou inventa sílabas no fim das frases, e isso só se percebe de ouvido.
- O modelo traz 58 vozes embutidas, e a `Damien Black` existe nesta versão.

Amostras para escutar: [`amostras_tts/piper.mp3`](amostras_tts/piper.mp3) e [`amostras_tts/xtts.mp3`](amostras_tts/xtts.mp3) (MP3 a 96 kbps).

## Estado do servidor

**Antes (22:11 UTC):**
- Carga de 0,28 / 0,16 / 0,10, CPU 97% ociosa.
- 15,5 GiB de RAM (não 12 GB, como dizia o roteiro do teste), dos quais 12 GiB disponíveis.
- Swap: 2,4 de 4 GiB já ocupados por processos parados há tempo. Não havia troca ativa (si/so = 0).
- Disco: 142 GB livres.
- Serviços importantes:
  - systemd: `figurinhas`, `cloudflared`, `docker`, `smbd`/`nmbd`, `ssh` e PCP (`pmcd`, `pmlogger`).
  - Docker: 12 containers, do AgilizaJus (caddy, db, whatsapp-bot, rag-engine, stt-summarizer, mcp-server, cloudflared) e do Receba Royale (frontend, backend, umami, umami_db, cloudflared).
  - Node `dist/server.js` (~1 GB de RSS).
- Horários de pico e agendamentos:
  - backups às 03:00 (Postgres do AgilizaJus), 04:00 (SSD) e 04:30 (Receba Royale);
  - bots às 05:00, 06:10, 15:40 e de hora em hora (:17 e :25);
  - auto-deploy a cada 5 min e logrotate às 00:00.
  - Por isso escolhi a janela das 22h, longe dos backups.

**Durante:**
- A carga de 1 min chegou a ~3,5 (limite do script: 10) e o uso de CPU a no máximo 21%.
- Memória disponível mínima: 8,9 GiB.
- **Uma rajada de swap** (si+so ≈ 600–900 KB/s numa amostra de 5–10 s) quando o XTTS carregava o modelo. O swap usado subiu só ~6 MB (2.535 → 2.542 MB) e a troca voltou a 0 em seguida. Por isso não interrompi o teste, mas registro aqui. Em produção, isso deve se repetir a cada carga do modelo.

**Depois (22:21 UTC):**
- 13 GiB disponíveis.
- Todos os 12 containers continuavam "Up", e os 4 com healthcheck estavam "healthy". `figurinhas` e `cloudflared` seguiam ativos.
- Não vi lentidão nem erro em nenhum serviço.
- Nenhum processo do teste ficou rodando (`pgrep -af bench_tts` vazio).

## Versões instaladas

Python 3.12.3, torch 2.15.0+cpu, torchaudio 2.11.1+cpu, torchcodec 0.17.0, coqui-tts 0.28.0, piper-tts 1.8.0, kokoro 0.9.4 (misaki 0.9.4), transformers 5.22.2, onnxruntime 1.31.1, numpy 2.5.4. A lista completa está em `server/bench_tts/saida-pip-freeze.txt`.

## Desvios do roteiro e o que foi pulado

- **Kokoro pulado.** O `espeak-ng` não está instalado no sistema (`which espeak-ng` sem resultado), e não usei sudo/apt. Para testar o Kokoro, o proprietário precisa rodar `sudo apt install espeak-ng`, e então basta `--motores kokoro`. O pacote Python já está no `.venv-tts`.
- **Instalações a mais para o XTTS.** O `coqui-tts` 0.28 não roda só com o que o roteiro instala. Foi preciso adicionar:
  - `torchaudio` (do índice CPU);
  - `coqui-tts[codec]`, que traz o `torchcodec`, obrigatório a partir do PyTorch 2.9;
  - `six`, que faltava nas dependências.

  O `torchaudio` mais novo é o 2.11.1, enquanto o torch está no 2.15. A combinação importou e reamostrou áudio sem erro, e o XTTS rodou completo. Mesmo assim, ao implementar a reserva, convém fixar essas versões. O roteiro de instalação deve trocar a linha do pip por:
  `pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu` e `pip install piper-tts "coqui-tts[codec]" kokoro soundfile numpy six`.
- **O `bench_tts.py` não foi alterado.**
- **Teste opcional com 8 threads não feito.** Durante a carga do XTTS houve a rajada de swap descrita acima. Como a geração roda de madrugada, com horas de folga, ganhar alguns minutos não compensa pressionar mais o servidor.
- A primeira tentativa (às 22:14) falhou no XTTS por falta do `torchaudio`. A tabela acima é da segunda rodada completa (Piper + XTTS), feita depois do ajuste.

## Recomendação

O **XTTS-v2** é o candidato a voz de reserva, **se** a amostra soar bem de ouvido. Os números cabem com folga no cenário da madrugada: ~4,5 min por edição, 4,4 GB de pico (abaixo do teto de 7 GB) e pouca CPU com 4 threads. O cuidado é carregar o modelo uma vez por edição e liberar a RAM ao terminar, como o script faz, e não rodar em horário de backup.

O **Piper** fica como reserva da reserva. Gera em segundos com 335 MB, mas a voz é mais robótica. Ele serve se o XTTS falhar ou travar, e também se o proprietário achar que a qualidade do XTTS não compensa.

O Kokoro só pode ser avaliado depois da instalação do `espeak-ng`.

A decisão é do proprietário, depois de escutar as amostras. O `.venv-tts` e os modelos (~2,2 GB + ~1,9 GB) ficaram em `despertador/server` para reaproveitar.
