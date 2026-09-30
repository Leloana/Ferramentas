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
13. **LRCLIB por duração**: usar `/api/get` com a duração do vídeo e só aceitar LRC sincronizado cuja duração bata (±2 s); estimar um offset global cruzando inícios de linha com o início da voz no stem.
14. Encaixar inícios de palavra no ataque de energia do stem (±150 ms) e dividir versos > 8 s / 10 palavras na maior pausa.

### Remoção de vocal
15. **`htdemucs_ft`** (`KARAOKE_DEMUCS_MODEL=htdemucs_ft`): um pouco menos de voz vazando no instrumental, ~4× mais lento. Comparar de ouvido em 5 músicas.
17. **Mudança de tom no navegador** (`jungle.js`) soa robótica acima de ±3 semitons e atrasa ~100 ms sem compensação na letra. Rápido: compensar o atraso quando `transpose ≠ 0`. Maior: gerar a versão transposta no servidor (rubberband).
18. **Cache de stems por vídeo do YouTube** (reinstalar sem baixar e separar de novo).
19. Rotas só de API (`/api/upload-song`, `/api/reinstall-song`) seguram o `whisper_lock` durante download + Demucs; o front usa só a fila, mas se voltarem a ser usadas, pegar o lock só no alinhamento.

## Feito na terceira rodada (2026-09-30) — validar no servidor

Código e testes sem GPU prontos; os limiares são primeiro chute.

### 1. As duas passadas do Whisper ficam gravadas
- `stt_engine.transcribe(..., details={})` preenche `prompted_words`, `unprompted_words` (None se não rodou) e `used` (`"prompted"` | `"unprompted"`; None = silêncio). O retorno `(texto, palavras)` não mudou. O portão virou `stt_engine.pick_transcription` (mesma regra ao vivo e no teste).
- `recorder.add_segment_result` grava os três campos (já no tempo do `sing_start`) quando o Whisper rodou; `session.json` passou a `format: 2`. Sessões e fixtures antigas continuam valendo (leitores usam `.get`).
- `test_recorded_sessions.rescore_session`: com as duas passadas aplica o portão atual (`PROMPT_TRUST_MIN_PROB`); fixture antiga usa `words` como antes. `replay_recording.py` marca com `*` os versos em que valeu a passada sem dica.
- **No servidor:** gravar partidas novas (formato 2), exportar para `tests/fixtures/recorded_sessions/` com gabarito e só então calibrar `PROMPT_TRUST_MIN_PROB` e os itens 2–10.

### 11–12. MMS_FA por linha, confiança e portão de qualidade
- `lrc_pro.align_lyrics_forced(..., synced_lrc=)`: com LRC, cada linha é alinhada na janela `[início − 1 s, próximo início + 0,5 s]` (máx. 30 s; a marca de fim do LRC encurta; começa depois da última palavra da linha anterior) no `vocal.mp3`. Linha que falha vira proporcional às sílabas a partir do início do LRC (~0,3 s/sílaba), sem atravessar a pausa. Sem LRC: letra inteira de uma vez, como antes. LRC que parece fora de sincronia (> 30% das linhas sem alinhar ou mediana da confiança < 0,35) tenta também a letra inteira e fica com a melhor nota do `assess`. O reinstall PRO passa o LRC revisado > LRCLIB > LRC anterior. Áudio lido pelo PyAV (`load_audio_full`), não mais `torchaudio.load`.
- Confiança por palavra = média das probabilidades dos tokens (`TokenSpan.score`) ponderada pelos quadros; `segments.json` ganha `lyrics_timed[].confidence`, e por verso `confidence` e `align` (`window` | `fallback` | `global`). O alinhador é injetável (`align_fn`): testes com emissão falsa em `test_lrc_pro_windows.py`.
- `utils/alignment_quality.assess(segments, audio_duration, vocal_rms_frames)` → `{"score", "flags", "lines": [{"idx", "confidence", "flags"}], "metrics"}`: palavras com confiança < 0,35 e mediana, empilhadas (≥ 3 a < 60 ms), versos > 12 s, palavras < 80 ms, depois do `sing_end`/fim do áudio, sobreposições e palavras no silêncio do stem (< −30 dB do p95). Sem confiança, só as estruturais.
- `meta.json["alignment_quality"]` e `meta.json["needs_review"]` (nota < `REVIEW_SCORE_MIN` = 70), gravados pelo `prepare_song` (não-debug), pelo PRO do reinstall, pela restauração de backup e depois do `realign_segments`. Nas fixtures (sem confiança): cru → depois do `finalize_segments`: Wolf 47 → 82 (sobreposições; sobram 75 palavras empilhadas a 50 ms), Geni 89 → 94, Zé 78 → 93.
- Falta: mostrar "revisar" na fila/lista e destacar as linhas fracas no editor (front).
- **No servidor:** rodar o PRO em 5–10 músicas com LRCLIB e conferir (a) que não há mais OOM e o tempo por música, (b) a distribuição da confiança em linhas certas × erradas para acertar `LOW_CONFIDENCE` e os pesos de `WEIGHTS`, (c) se o LRCLIB fora de sincronia (item 13) derruba a nota como deveria, (d) se o MMS_FA estica a última palavra pela pausa quando a janela chega a 30 s sem marca de fim.

### 16. Volume do instrumental normalizado
- `utils/loudness.py`: LUFS integrado (BS.1770: K-weighting por FFT em pedaços de 30 s, portões −70 LUFS / −10 LU) em numpy, sem scipy/ffmpeg; ganho para −16 LUFS (máx. +12 dB, ignora < 0,5 dB) e limitador com antecipação de 5 ms para o pico por amostra ficar em −1,5 dBFS (−1 dBTP com 0,5 dB de folga, sem oversampling). 4 min estéreo: ~3 s de CPU.
- `separation.export_backing_mp3` normaliza e exporta o `backing_track.mp3` (fila e reinstall, inclusive instrumental baixado do YouTube) e grava `meta.json["loudness"] = {"lufs_before", "gain_db"}`. Falha só loga e exporta o original. O `vocal.mp3` (voz guia, alinhamento, afinação) não é mexido.
- **No servidor:** ouvir 5 músicas antes × depois (limitador em músicas com muito pico), conferir o `lufs_before` contra o `ffmpeg -af ebur128` e reinstalar as músicas antigas para igualar o volume. A voz guia fica com o volume relativo diferente do de antes nas faixas que ganharam/perderam muito.

## Recursos novos (2026-09-30, segunda rodada)

- **Afinação** (`server/pitch.py`): YIN em numpy (4 min de áudio em ~1 s na CPU). A referência sai do `vocal.mp3` (gerada logo depois da separação ou, nas músicas antigas, em segundo plano na 1ª partida) e fica em `pitch.json`. Cada verso ganha "tom X%" — oitava livre, ±0,25 s de folga, e a nota mostrada já desconta o acaso (altura aleatória fazia ~30). **Não entra na nota** até calibrar com canto real; o tom da trilha (transposição) é enviado pela TV. Pontos a observar no servidor: gate de RMS do mic (`MIC_RMS_GATE`), harmonias no stem, vazamento da TV no microfone.
- **Voz guia**: `vocal.mp3` tocando junto do instrumental (controle "Voz guia", 0% = desligada), passando pelo mesmo tom.
- **Revezar versos**: cada verso com letra é de um time em rodízio; o servidor pontua só o dono e a média de cada um é sobre os versos dele.
- **Perfis/recordes**, **cartão para print**, **ouvir a apresentação**, **contagem 3-2-1**, **tela acesa no celular**, **painel de saúde**, **cache do instrumental** (`Cache-Control` de 1 dia).
