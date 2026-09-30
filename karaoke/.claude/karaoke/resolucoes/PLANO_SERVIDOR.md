# Plano no servidor (máquina com GPU)

Roteiro para as próximas idas ao servidor real. O objetivo principal é **juntar dados de partidas
reais com anotação** — é o que falta para calibrar a nota, a afinação e o alinhamento. O checklist
de infraestrutura (túnel, iPhone) fica em [TODO_SERVIDOR_FINAL.md](TODO_SERVIDOR_FINAL.md); o que
cada ajuste de áudio significa, em [AUDIO_PIPELINE_MELHORIAS.md](AUDIO_PIPELINE_MELHORIAS.md).

Comandos em PowerShell, na pasta `karaoke/` com a `venv` ativa (`.\venv\Scripts\Activate.ps1`).

---

## Antes de ir (no computador de desenvolvimento)

- [ ] **Gravação completa** (opcional, mas quanto antes melhor — partida gravada sem esses dados não
      volta a ter). Hoje a gravação guarda a voz de cada celular, as duas passadas do Whisper e a nota
      por verso. Faltam:
      1. afinação por verso e cópia do `pitch.json`;
      2. configuração da partida (tom, velocidade, sincronia, volumes, times, revezamento);
      3. linha do tempo da TV (play, pausa, seek, velocidade);
      4. celular e rede (modelo/navegador, taxa do mic, atraso, buracos no áudio);
      5. ruído de fundo de cada celular nas pausas;
      6. dados crus do Whisper (no_speech_prob, avg_logprob, idioma detectado);
      7. tempo até a nota e espera pela GPU por verso;
      8. versão de tudo (commit, constantes da nota, origem e qualidade da letra);
      9. anotação do próprio cantor no celular no fim da música.
- [ ] **Ferramenta de exportar** partidas anotadas para `tests/fixtures/recorded_sessions/` (como as três atuais).

## 1. Preparar (uma vez, ~30 min)

- [ ] `git pull` na raiz `Ferramentas/`.
- [ ] Dependências: `pip install -r requirements.txt` e, para a GPU,
      `pip install --force-reinstall torch torchaudio --index-url https://download.pytorch.org/whl/cu124`.
- [ ] Opcional para os testes de tela: `pip install playwright` e `python -m playwright install chromium`.
- [ ] **Backup** do acervo antes de reprocessar: copiar `server/songs/` e `players/` para outro disco.
- [ ] **Suíte completa**: `python -m pytest -q tests` — tem que passar tudo, inclusive
      `tests/test_escolta_vagalumes.py` (é o único que usa CUDA e áudio de verdade). Depois
      `python -m pytest tests/ui`. Anotar qualquer falha antes de seguir.
- [ ] Subir o servidor (comando do README ou `.claude/karaoke/Executar.md`) e abrir o **painel de
      saúde** (clique no "Online" da TV): GPU livre, Whisper certo, disco com folga.

## 2. Reprocessar o acervo (~5 min por música, deixa rodando)

As músicas antigas não têm volume nivelado, `pitch.json`, nota de qualidade nem versos corrigidos
no alinhamento. Com o servidor rodando, o reinstall é delegado a ele (respeita o mutex de GPU):

```powershell
# uma música (com alinhamento PRO)
python tools\reinstall_song.py server\songs\geni-e-o-zepelim-chico-buarque --align-lyrics
# todas
Get-ChildItem server\songs -Directory | ForEach-Object { python tools\reinstall_song.py $_.FullName --align-lyrics }
```

- [ ] Letra revisada à mão no editor é mantida (marca `.lyrics_edited`), a não ser com `--align-lyrics`.
      Para essas, rodar **sem** `--align-lyrics`.
- [ ] Depois, na lista: as músicas com selo **"Revisar"** — abrir no editor e corrigir. Anotar quantas
      foram marcadas e se a marcação faz sentido (música boa marcada ou ruim sem marca = ajustar
      `REVIEW_SCORE_MIN` / pesos em `server/utils/alignment_quality.py`).
- [ ] **Volume**: ouvir 3–4 músicas antes e depois (o antigo está no backup). Conferir em uma:
      `ffmpeg -i server\songs\<slug>\backing_track.mp3 -af ebur128 -f null -` ≈ −16 LUFS.
- [ ] **Separação**: em 5 músicas, comparar `htdemucs` (padrão) com `htdemucs_ft`
      (`$env:KARAOKE_DEMUCS_MODEL="htdemucs_ft"` + reinstall numa cópia da pasta). Ouvir se sobra voz
      no instrumental e anotar o tempo.
- [ ] Capas: passar o olho na lista; trocar pelo lobby ("Trocar capa") as que vieram erradas.

## 3. Sessões de teste roteirizadas (o mais importante)

Cada cenário cobre um ajuste da calibração. Use 2–3 músicas conhecidas (uma em português, uma em
inglês, e uma em japonês se possível) e **anote todas** no fim (lápis do fim de jogo; certo /
errado / cantarolei por verso). Gravação sem anotação serve pouco.

| # | Cenário | Para calibrar |
| :-- | :--- | :--- |
| 1 | Cantar certo, bem, com fone | Referência: nota tem que ficar alta |
| 2 | Cantar certo **sem fone** (TV alta) | Vazamento da TV no mic, confiança do Whisper |
| 3 | Cantarolar a música inteira ("na na na") | Nota tem que ficar baixa |
| 4 | Cantar a **letra errada** de propósito (outra música por cima) | Cópia da dica pelo Whisper |
| 5 | Entrar **atrasado** ~0,5–1 s em todos os versos | Tolerância de tempo |
| 6 | Cantar **desafinado de propósito** (letra certa) e depois afinado | Se o "tom X%" separa os dois |
| 7 | **Dois celulares**, um cantando e outro **calado ao lado** | Celular que capta o vizinho |
| 8 | Celular longe da boca (~50 cm) e sala barulhenta | Gate de silêncio / ruído de fundo |
| 9 | Revezar versos com 2 pessoas | Duelo, "Vez de…", médias por versos próprios |
| 10 | Música em japonês | Filtro de confiança do japonês (hoje frouxo) |

- [ ] Em cada partida, olhar o **painel de saúde**: "tempo até a nota" (mediana e 90%). Acima de ~3 s = anotar.
- [ ] Durante uma delas, **adicionar uma música pelo celular**: a partida segue; no fim, o INICIAR
      mostra "GPU ocupada" até a letra ficar pronta.
- [ ] Numa delas, **derrubar o Wi-Fi da TV** por uns segundos: o placar não pode zerar. E fechar/abrir
      o navegador de um celular: registrar o mesmo apelido e confirmar que volta a pontuar.

## 4. Noite de festa (uso normal, gravando)

- [ ] Jogar normalmente com a **fila da noite** (pedir pelo celular), cartão para print e "Ouvir".
- [ ] Anotar à parte o que incomodou (nota injusta num verso, letra fora de tempo, capa errada,
      tela que travou). Um bloco de notas com "música + verso + o que houve" vale ouro.
- [ ] Testar o navegador da TV de verdade (controle remoto) e um iPhone.

## 5. Trazer os dados

- [ ] Copiar `recordings/` (cada partida é uma pasta com `session.json`, `gabarito.json` e um `.wav`
      por cantor — ~4 MB por minuto com dois celulares) e `players/` para o disco de backup.
- [ ] Trazer as anotações do passo 4.
- [ ] Rodar o replay para ter a linha de base:
      `python tools\replay_recording.py --json linha_de_base.json`
- [ ] Com os dados em mãos, calibramos juntos (cada mudança conferida no replay e nos testes de
      partidas gravadas): confiança do Whisper (`PROMPT_TRUST_MIN_PROB`), detecção de voz, tolerância de
      tempo, respiro antes do verso, gate de silêncio por celular, celular vizinho, afinação na nota (ou não).

---

Ordem se o tempo for curto: **1 → 3 (cenários 1, 3, 4, 5 e 7) → 5**. O reprocessamento (2) pode
rodar sozinho, mas enquanto ele gera cada letra o INICIAR fica bloqueado (mutex de GPU): melhor
deixar rodando antes ou depois das partidas.
