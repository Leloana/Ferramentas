# Revisão do pipeline de áudio (2026-09-30)

Revisão de três partes: identificação de voz e nota, geração de letra e tempos,
remoção de vocal. A primeira parte deste arquivo é o que **já foi corrigido**
(testável sem GPU). A segunda é o que **precisa de áudio real no servidor**
para calibrar, com o experimento sugerido para cada item.

Medidas de referência (fixtures de `tests/fixtures/recorded_sessions/`,
repontuadas com `score_words`):

| | Zé | Wolf | Geni | Pares de letra errada (média / máx) |
| :--- | ---: | ---: | ---: | ---: |
| Antes | 94,19 | 79,24 | 82,61 | 5,50 / 51,4 |
| Depois | 94,19 | 79,23 | 83,05 | 5,54 / 51,4 |

## Corrigido

### Remoção de vocal
- **Fase 2 da fila separava de novo**: com `clean_existing`, a fase 2 limpava a pasta e baixava + rodava o Demucs outra vez, *segurando o `whisper_lock`* (a nota da partida parava). Agora a fase 2 usa `clean_existing=False`.
- **A limpeza da reinstalação apagava a letra** recém-gravada (vinha depois de gravar `lyrics.lrc`/`lyrics.txt`). Agora limpa primeiro.
- **Várias separações ao mesmo tempo na GPU** (cada música adicionada disparava a sua): `utils/separation.py` serializa.
- **MP3 a ~128 kbps** (padrão do LAME, depois de dois passos com perda): agora 320 kbps (`KARAOKE_MP3_BITRATE`).
- **`demucs` do PATH** (quebra sem venv ativo): `python -m demucs.separate` com o Python do servidor; falha na GPU tenta na CPU; o erro mostra o fim do stderr.
- Saída do Demucs (~80 MB de WAV) apagada também em erro/cancelamento.

### Letra e tempos
- **Realinhamento zerava os tempos** (`lrc_realign.realign_segments` lia `expected_start`, relativo ao verso, como absoluto): todos os versos iam para ~0 s. Era o caminho do "refazer com alinhamento" quando o MMS_FA falhava. Teste: `test_lrc_realign.py`.
- **Palavras empilhadas** quando o Whisper devolve número diferente de palavras: casamento em ordem + interpolação por sílabas (`segment_timing.match_words_in_order`).
- **Versos sobrepostos e última palavra fora do verso** (Wolf 42/59 versos sobrepostos, Zé 13/29 com a última palavra cortada): `finalize_segments` no `prepare_song`, no PRO (`lrc_pro`) e na leitura do `song_manager` (músicas antigas corrigidas sem reprocessar). Nas três fixtures: 0 sobreposições, 0 cortes.
- **LRC com várias marcas na linha** (`[00:12][01:30]refrão`) era descartado.
- **Letra revisada à mão era trocada** pela do LRCLIB/backup no reinstall: marca `.lyrics_edited`.

### Nota
- "Dá-se" cantado certo dava 43 (Whisper devolve "Dá" + "-se").
- "tá/está", "tô/estou", "cê/você", "pra/para", "à/a", números 0–20 por extenso.
- Cópia fantasma do verso com probabilidade < 0,1 disparava a penalidade de precisão (Geni 97: 65 → 85).
- Verso pontuado assim que o áudio de todos os celulares cobre a janela (antes esperava sempre a folga mínima de 0,6 s).
- `CLAUDE.md` dizia que a nota usa Double Metaphone: não usa (só o `lrc_realign`).

## Para calibrar no servidor (precisa de áudio real)

Ferramentas: `tools/replay_recording.py --set modulo.NOME=valor` sobre `karaoke/recordings/`, e os testes de `tests/unit/test_recorded_sessions.py` (gabarito do cantor).

### Identificação de voz
1. **O teste do gabarito não vê o que roda ao vivo** — só guarda as palavras da passada com dica; 11 versos teriam sido retranscritos sem a dica (Wolf 50 e 52 passam só porque o Whisper copiou a dica). *Fazer primeiro:* `stt_engine.transcribe` devolver as duas passadas e o `recorder` gravar ambas. Pré-requisito para calibrar o resto.
2. **Pouco respiro antes do verso**: a janela do verso começa depois do pós-roll do anterior; Geni 53/102 versos com < 0,2 s antes do `sing_start`, e 33/99 cantores entram antes. Primeira palavra perdida (Geni 14, 56). Proposta: fim do verso anterior em `min(sing_end, última palavra + 0,25)` e respiro mínimo de 0,3–0,5 s.
3. **Tolerância de tempo**: 1,0/2,5 s → 1,5/3,0 s dá 94,91 / 79,56 / 83,6 sem piorar os pares errados. Falta uma fixture de "cantou atrasado de propósito".
4. **VAD**: parâmetros padrão do Silero (limiar 0,5, padding 400 ms) cortam começo suave. Expor como constantes e testar limiar 0,3–0,35 / padding 200 ms, ou sem VAD (o gate de RMS já barra silêncio).
5. **Temperatura**: faster-whisper tenta até 6 temperaturas em canto sobre música (lento e gera palavras aleatórias). Testar `temperature=(0.0, 0.4)` e `beam_size` 1 × 5.
6. **Vários celulares**: cada um é transcrito em série e a repetição sem dica refaz o encoder. Codificar uma vez e gerar em lote (ctranslate2 `encode` + `generate`). Ganho ~N× no encoder.
7. **Gate de silêncio fixo** (`SILENCE_RMS = 0,0018`): medir o ruído de fundo de cada celular nas pausas.
8. **Celular calado perto de quem canta** pontua alto (ouve o vizinho). Com as mesmas palavras e RMS ~10 dB menor, zerar. Gravar uma sessão com dois celulares e um calado.
9. **Japonês**: o filtro de confiança aceita quase qualquer fragmento de kana. Gravar uma fixture em japonês.
10. **Ordem das palavras é ignorada** ("door the at wolf the" = 97) e o "sanduíche" dá 1,0 a palavra não cantada. Alinhamento monotônico e teto 0,7 no resgate — mexe em todas as notas, calibrar com o gabarito.

### Letra e tempos
11. **MMS_FA na música inteira de uma vez** (memória cresce com o quadrado da duração → erro → caía no realign quebrado). Alinhar por linha na janela do LRC (`[início − 1 s, próximo + 0,5 s]`), no stem de voz.
12. **Confiança por palavra** (`TokenSpan.score` do MMS_FA) e um **portão de qualidade** antes de marcar a música como pronta: % de palavras casadas, versos > 12 s, palavras < 80 ms, palavras caindo em silêncio no stem, diferença de duração LRC × áudio. Guardar `alignment_quality` no `meta.json` e mostrar "revisar" na fila; o editor destaca as linhas fracas.
13. **LRCLIB por duração**: usar `/api/get` com a duração do vídeo e só aceitar LRC sincronizado cuja duração bata (±2 s); estimar um offset global cruzando inícios de linha com o início da voz no stem.
14. Encaixar inícios de palavra no ataque de energia do stem (±150 ms) e dividir versos > 8 s / 10 palavras na maior pausa.

### Remoção de vocal
15. **`htdemucs_ft`** (`KARAOKE_DEMUCS_MODEL=htdemucs_ft`): um pouco menos de voz vazando no instrumental, ~4× mais lento. Comparar de ouvido em 5 músicas.
16. **Volume entre músicas** varia 6–10 dB: medir LUFS (ffmpeg `ebur128`) e normalizar o instrumental (~−16 LUFS) ou guardar o ganho no `meta.json`.
17. **Mudança de tom no navegador** (`jungle.js`) soa robótica acima de ±3 semitons e atrasa ~100 ms sem compensação na letra. Rápido: compensar o atraso quando `transpose ≠ 0`. Maior: gerar a versão transposta no servidor (rubberband).
18. **Cache de stems por vídeo do YouTube** (reinstalar sem baixar e separar de novo).
19. Rotas só de API (`/api/upload-song`, `/api/reinstall-song`) seguram o `whisper_lock` durante download + Demucs; o front usa só a fila, mas se voltarem a ser usadas, pegar o lock só no alinhamento.
