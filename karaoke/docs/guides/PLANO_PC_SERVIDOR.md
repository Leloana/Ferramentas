# Plano para o PC do servidor (deixado em 2026-10-02)

O PC de desenvolvimento não tem GPU nem o áudio das músicas: tudo o que está aqui só dá para fazer
na máquina do servidor. Ordem sugerida: de cima para baixo. Cada passo diz **o que rodar** e **o que
conferir**. A lista completa de pendências continua em [TODO_SERVIDOR_FINAL.md](TODO_SERVIDOR_FINAL.md);
os detalhes de áudio, em [AUDIO_PIPELINE_MELHORIAS.md](AUDIO_PIPELINE_MELHORIAS.md).

Comandos em PowerShell, de dentro de `karaoke/`, com o venv ativo (`.\venv\Scripts\Activate.ps1`).

## 0. Atualizar e rodar a suíte (5 min)

```powershell
git pull
python -m pytest -q tests          # 276 em 2026-10-01; agora ~290 (cartões, fila, pronúncia, frases-fantasma)
```

Tudo verde antes de seguir. *(2026-10-05: 337 passaram, 1 pulado.)* Nenhuma dependência nova: a pronúncia usa o `Metaphone` que já estava no
`requirements.txt`. Os testes de japonês precisam de `fugashi`, `pykakasi` e `unidic-lite` (já no requirements).

## 1. O que entrou desde a última vez e precisa ser conferido de verdade

### 1.1 Capas em 1200 px (2 min)

```powershell
python tools/upgrade_covers.py      # troca as capas de 600 px pela versão grande da mesma imagem
```

- [x] Saída: "N capa(s) trocada(s)". Música que a pessoa escolheu outra capa na TV continua com a escolhida.
      *(2026-10-05: 25 de 66 trocadas.)*
- [ ] Abrir o cartão do fim (estilo **Vidro**) numa música qualquer na TV: a capa não pode ficar borrada.

### 1.2 Cartões novos na TV e no celular (10 min, numa partida curta)

Nove estilos agora: caderno, neon, vidro, ingresso, cupom, vinil, pôster, mosaico, letreiro.

- [ ] **TV de verdade** (o navegador antigo): lista de estilos à direita, ↑↓/←→ trocam, OK/Voltar fecham.
- [ ] Fontes novas (Archivo, IBM Plex Mono, Anton) carregaram? Se a TV não baixar do Google Fonts, cai
      no sans/mono do sistema — conferir se continua legível.
- [ ] **Mosaico**: o fundo é a capa em quadrados grandes (12×15). Se aparecer borrado em vez de quadrado,
      a TV não suporta `image-rendering: pixelated` — anotar o modelo.
- [ ] **Pôster**: a capa em retícula (pontos). Se a TV mostrar tudo preto/amarelo liso, ela não faz
      `mix-blend-mode` — anotar.
- [ ] **Ingresso e Cupom**: o código de barras tem um traço por verso (vem do `game_over` novo,
      `player_stats[p].verses`). Verso fora = traço baixo/vermelho no ingresso.
- [ ] Celular: a barra de estilos rola de lado; tirar print de 2–3 estilos e ver se nada corta.

### 1.3 Nota pela pronúncia — **a auditoria mais importante** (20 min, GPU)

A nota agora aceita palavra escrita diferente mas com o mesmo som ("belly shot" × "Belisha",
"praquefazer" × "pra que fazer", "xuva" × "chuva"). No PC de dev só deu para provar que **não piora**
(Gaara, 3 partidas, 866 pares de letra trocada). Falta provar que **sobe** onde devia:

```powershell
# com a pronúncia (padrão)
python tools/replay_recording.py recordings/20261001-234606_tipo-madara-mhrap recordings/20261001-235019_renegado-mhrap recordings/20261002-000811_o-rap-mais-insano-dos-uchihas-mhrap recordings/20261002-002922_my-iron-lung-radiohead --json pron_on.json
# sem a pronúncia (como era)
python tools/replay_recording.py <as mesmas 4 pastas> --set score_engine.PHONETIC_MATCH=1000 --set score_engine.SPAN_MAX=1 --json pron_off.json
```

- [x] Os 4 sobem com a pronúncia (referência sem ela: Madara 65, Renegado 83, Uchihas 72).
      *(2026-10-05, sem → com: Madara 65,5 → 65,5 · Renegado 83,0 → 82,8 · Uchihas 72,6 → 72,9 ·
      Iron Lung 73,3 → 73,9 (erro vs gabarito 23,4 → 23,2). Quase tudo que mudou nos raps foi o Whisper
      transcrevendo diferente entre as duas rodadas, não a pronúncia: ele não é determinístico entre
      rodadas. Com a MESMA transcrição, só mudaram: Iron Lung 26/48/54 (Belisha, abaixo), Uchihas #65
      "eh o bicho" 88 → 100 (certo) e Uchihas #38 0 → 9 (texto sem relação, ganho desprezível).)*
- [x] My Iron Lung: os versos "My Belisha beacon" passam a pontuar.
      *(26 → 65 "my bella shot be con", 33 → 67 "my belly shot", 26 → 39 "my belly shot that can".)*
- [ ] Olhar os versos que **mais** subiram: o que o Whisper ouviu é mesmo o verso cantado? Se aparecer
      um falso acerto (palavra sem relação valendo), anotar o par — os limiares são `PHONETIC_MATCH` (85),
      `PHONETIC_MIN_SPELLING` (55) e `SPAN_MATCH` (85) em `server/score_engine.py`.
- [x] Repetir com a japonesa `20261001-195510_aoi-koi-...` — tem que dar **igual** (a pronúncia não vale no japonês).
      *(72,2 → 73,5, mas só nos versos 27 e 28, onde o Whisper ouviu outra coisa em cada rodada; com a
      mesma transcrição a nota é igual.)*

### 1.4 Gabarito dos raps (15 min, celular)

Sem gabarito, a medição acima é só "subiu/desceu". No celular, abrir cada partida em "Anotar meus versos"
(Madara, Renegado, Uchihas, My Iron Lung) e marcar certo/errado/cantarolei. Depois:

```powershell
python tools/export_recordings.py recordings/<as 4 pastas>     # vira fixture em tests/fixtures/recorded_sessions/exported/
python -m pytest -q tests/unit/test_recorded_sessions.py
```

- [ ] Fixtures geradas com `baseline` (erro médio). Commitar: viram a trava para as próximas mudanças na nota.

### 1.5 Fila de processamento em disco (10 min)

- [ ] Adicionar uma música pela fila e **derrubar o servidor** no meio do download ou da separação.
- [ ] Ao subir de novo: log `[QUEUE] Retomando da fila gravada: '<título>'` e a música termina sozinha
      (sem baixar de novo se o `original.mp3`/stems já estavam lá).
- [ ] Arquivo `server/songs/.queue.json` some quando a fila esvazia.

### 1.6 Frases-fantasma em japonês e palavra partida no LRC (5 min)

- [x] Replay da aoi-koi: os versos onde aparecia "ご視聴ありがとうございました" agora vêm vazios (log
      "Alucinação do Whisper detectada e expurgada"). *(2026-10-05: a frase estava no session.json gravado e
      sumiu no replay.)*
- [x] Reinstalar o My Iron Lung **sem** a letra revisada (ou baixar a letra de novo numa cópia): "My un-" /
      "cle Bill" tem que chegar como "My uncle Bill". *(2026-10-05: `fetch_lyrics` no lrclib → 6× "My uncle Bill".)*

## 2. Áudio (separação, volume, letra no tempo)

### 2.1 Ouvir RoFormer × Demucs (20 min, fone)

Os instrumentais já estão em `validacao_gpu/separacao-*/` (Hysteria, Construção, Oh No!).

- [ ] Ouvir os pares `*-instrumental.wav`: sobra voz de fundo? pratos/reverb sujos? O RoFormer custa
      ~1 min a mais por música na fila.
- [ ] Decidir: manter `auto` (RoFormer) ou fixar `KARAOKE_SEPARATOR=demucs`. Anotar a decisão no TODO.
- [ ] Opcional: `KARAOKE_DEMUCS_MODEL=htdemucs_ft` em 5 músicas (menos voz vazando, ~4× mais lento).

### 2.2 Volume do instrumental (10 min)

- [ ] Tocar 4–5 músicas seguidas (antigas e novas): o volume tem que ficar parelho (~−16 LUFS,
      `meta.json["loudness"]`). Faixa com muito pico soando esmagada = limitador forte demais.

### 2.3 Letra no tempo do áudio — as suspeitas do item 7 (30 min, editor de letra)

Tocar no editor de letra e comparar com `validacao_gpu/<slug>.sync_preview.lrc`:

- [ ] `hey-pixies` (encaixe +23,7 s com concordância 0 — o mais provável de estar errado)
- [ ] `dia-clarear-banda-do-mar`, `hysteria-muse`, `flores-astrais-ney-matogrosso`
- [ ] `insista-em-mim-ana-frango-eletrico` (+11,45 s) e `take-a-bite-beabadoobee` (+9,45 s): intro longa?
- [ ] `o-vira-ney-matogrosso`, `samurai-djavan`, `dela-ana-frango-eletrico`

Método errado → anotar concordância e cobertura (`MIN_AGREEMENT` 0,6 e `PLAN_MIN_COVERAGE` 0,35 em
`server/utils/lrc_sync.py`).

### 2.4 Reprocessar o acervo (deixar rodando, fora de partida)

Depois de 2.1 e 2.3 (para reprocessar já com a decisão do separador e dos limiares):

```powershell
Copy-Item -Recurse server/songs ../songs_backup_2026-10   # backup antes
python tools/reinstall_song.py server/songs/<slug>                  # uma por vez, modo rápido
python tools/reinstall_song.py server/songs/<slug> --align-lyrics   # nas que já eram PRO (segments com "align")
```

- [ ] Primeiro as 16 com verso que engole o solo (lista no TODO; piores: fala-ney-matogrosso,
      dela-ana-frango-eletrico, you-radiohead).
- [ ] Música com `.lyrics_edited` mantém a letra revisada (Monster, Gaara, Óbito, Iron Lung) — conferir.
- [ ] No fim, ver a lista de "Revisar" na TV.

### 2.5 Calibrações com canto real (quando houver noite de partida gravando)

Cada uma é um `--set` no `replay_recording.py` contra as partidas com gabarito; só mudar o padrão se o
erro médio cair e a letra trocada continuar baixa:

- [ ] **Respiro antes do verso** (1ª palavra perdida): fim do verso anterior em `min(sing_end, última palavra + 0,25)`.
- [ ] **Tolerância de tempo** 1,0/2,5 s → 1,5/3,0 s (`TIMING_TOLERANT_SEC` / `TIMING_LENIENT_SEC`).
- [ ] **VAD**: limiar 0,3–0,35 e padding 200 ms, ou sem VAD.
- [ ] **Temperatura** `(0.0, 0.4)` e `beam_size` 1 × 5 (tempo e acerto).
- [ ] **Rap muito rápido** (Uchihas): transcrever 3–4 versos juntos (~8 s) e repartir as palavras.
- [ ] **Celular calado perto de quem canta**: gravar uma sessão com dois celulares e um calado.
- [ ] **Afinação** ("tom X%"): separa afinado de desafinado? Só depois pensar em pôr na nota.

## 3. Partida de verdade (checklist de festa)

- [ ] 2–4 celulares, duplas/trios, revezamento ("Vez de…"), carimbo, cartão no fim, "Ouvir".
- [ ] Derrubar o Wi-Fi da TV no meio: volta sem zerar o placar. Celular que cai: mesmo apelido volta a pontuar.
- [ ] Fila da noite: pedir pelo celular, "Próximas" na TV, contagem de 10 s abrindo a próxima.
- [ ] Adicionar música durante a partida: fase 1 roda junto; INICIAR mostra "GPU ocupada" na fase 2.
- [ ] iPhone pelo domínio: microfone liberado, verso cantado certo perto de 100, tela acesa a música inteira.

## 4. Trazer de volta para o PC de dev

```powershell
python tools/export_recordings.py --zip ../partidas_2026-10.zip   # partidas com .wav, para depurar sem cantar
```

Commitar as fixtures novas (1.4) e as decisões (2.1, 2.3) no TODO. Uma partida inteira com WAV e
gabarito, como `tests/fixtures/replay/rap-do-gaara-lelo`, é o que permite mexer na nota longe da GPU.
