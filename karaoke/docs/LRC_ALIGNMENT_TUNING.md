# LRC Alignment Tuning Guide

Quando o `lyrics.lrc` gerado sai com timestamps ruins, este é o
playbook. Cada sintoma aponta para 1-2 knobs específicos.

**Arquivos onde os knobs vivem:**
- `karaoke/server/utils/lrc_align.py` — alinhamento letra ↔ Whisper
- `karaoke/server/utils/whisper_params.py` — VAD / transcrição
- `karaoke/server/stt_engine.py` — gate de silêncio do Whisper

Sempre rode `reinstall_song.py` na música depois de mexer num knob — o
LRC é regenerado do zero a partir do `meta.json` + `vocal.mp3`.

---

## Como avaliar a qualidade rapidamente

Abra o `.lrc` gerado e procure:

1. **Sequência de timestamps próximos** (ex: 5+ linhas com gap < 0.3s).
   Sinal claro de colisão.
2. **Primeiras linhas com `[00:00.00]` ou negativas**. Extrapolação
   inicial quebrada.
3. **Últimas linhas grudadas no fim do áudio** (ex: 3 linhas dentro de
   1s no fim). Extrapolação final quebrada.
4. **Refrão repetido aparecendo só em uma posição**. Cursor não está
   avançando entre ocorrências.
5. **Linhas "vazadas" pro verso seguinte** (ex: "I beg to dream..." em
   `[00:45.92]` quando o canto real começa em 00:46.50). Word matching
   pegou âncora errada.

Aplique a tabela abaixo conforme o sintoma dominante.

---

## Tabela de sintoma → knob

### 🔴 Versos colidindo (N linhas em 1-2 segundos)

```
[01:46.79]On holiday
[01:47.03]Hear the drum...
[01:47.27]Another protester...
```

**Causa**: Whisper agrupou vários versos num segmento sem pausa
suficiente entre eles, e a fração de palavras casadas ficou abaixo do
mínimo, caindo no fallback linear.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `whisper_params.py` | `VAD.min_silence_duration_ms` | 700 | **400** (separa versos com pausa curta) |
| `whisper_params.py` | `VAD.threshold` | 0.25 | **0.18** (detecta mais como fala) |
| `lrc_align.py` | `WORD_MIN_FUZZ_RATIO` | 80 | **70** (mais tolerante a erros do Whisper) |

Se ainda colidir: aumentar `WORD_SEARCH_WINDOW` de 40 → 80. Janela
maior permite que palavras da letra encontrem matches mesmo quando
Whisper transcreveu palavras a mais entre elas.

---

### 🔴 Linhas no começo todas em `[00:00.00]` ou negativas

**Causa**: poucas palavras casaram no início, e o algoritmo extrapolou
para trás com taxa muito alta (palavras "sobreviventes" foram empurradas
para tempo negativo, depois clampadas em 0).

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `lrc_align.py` | `RATE_MIN_SEC_PER_WORD` | 0.15 | **0.25** (palavras na borda mais espaçadas) |
| `lrc_align.py` | `WORD_SEARCH_WINDOW` | 40 | **80** (acha mais matches no início) |

Se persistir: o problema pode ser **VAD pulando o vocal inicial**. Veja
seção "Whisper deixa de transcrever".

---

### 🔴 Últimas linhas em `[xx:xx.xx]` muito próximas do fim do áudio

```
[03:25.00]Penúltimo verso
[03:25.20]Último verso
[03:25.50]
```

**Causa**: oposto do anterior — extrapolação final usou taxa alta
porque as últimas 2 âncoras estavam muito próximas.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `lrc_align.py` | `RATE_MAX_SEC_PER_WORD` | 1.5 | **1.0** (cap mais conservador no fim) |
| `lrc_align.py` | `DEFAULT_SEC_PER_WORD` | 0.4 | (só usado quando há 1 âncora) |

Se a última âncora real está muito longe do fim, considere se o
Whisper transcreveu até o fim do áudio — checar log de `reinstall_song`.

---

### 🔴 Refrão aparece sempre na mesma posição

```
[01:30.00]I beg to dream...   ← OK
[01:35.00]                     ← interpolado
[01:40.00]                     ← interpolado
[01:42.00]I beg to dream...   ← ❌ Deveria estar em ~02:50
```

**Causa**: cursor forward-only requer que pelo menos algumas palavras
**entre** as 2 ocorrências do refrão tenham casado, para que o cursor
avance. Se nada casou no meio (verso intermediário com Whisper errado),
o cursor fica próximo e a 2ª ocorrência mapeia errado.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `lrc_align.py` | `WORD_MIN_FUZZ_RATIO` | 80 | **70** ou **65** |
| `lrc_align.py` | `WORD_SEARCH_WINDOW` | 40 | **80** ou **120** |

Janela maior + ratio menor = chance maior de ancorar palavras
intermediárias e empurrar o cursor para frente.

**Se persistir:** o vocal intermediário entre refrões pode estar
suprimido pelo Demucs (instrumental forte). Verifique manualmente que
o `vocal.mp3` contém aquele trecho audível.

---

### 🔴 Whisper deixa de transcrever um verso que existe no áudio

Não tem timestamp do verso porque o Whisper nem viu aquele trecho.

**Causa**: VAD considerou silêncio (threshold alto demais) ou o gate de
RMS do `stt_engine.transcribe` filtrou.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `whisper_params.py` | `VAD.threshold` | 0.25 | **0.15** |
| `whisper_params.py` | `VAD.speech_pad_ms` | 200 | **400** (mais respiração ao redor da fala) |
| `stt_engine.py` | `rms_threshold` em `transcribe()` | 0.00005 | **0.00001** |

**Risco**: thresholds mais baixos aumentam **alucinações** ("Thanks
for watching", "Subscribe to my channel"). O regex
`_HALLUCINATION_RE` em `stt_engine.py` filtra os mais comuns, mas se
aumentar o ruído, pode passar coisa nova. Olhe os logs.

---

### 🔴 Whisper "alucinando" — frases tipo "Thanks for watching"

**Causa**: VAD pegou silêncio ou ruído ambiente como fala.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `whisper_params.py` | `VAD.threshold` | 0.25 | **0.35** (mais restritivo) |
| `stt_engine.py` | `rms_threshold` | 0.00005 | **0.0001** |
| `stt_engine.py` | `_HALLUCINATION_RE` | regex EN/PT | adicione padrões novos |

Se aparecer um padrão novo de alucinação, adicione no regex em
`stt_engine.py`. Padrões comuns extras:
```
"like and subscribe"
"see you next time"
"video patrocinado"
"obrigado por assistir"
```

---

### 🔴 Linha 1 do LRC tem timestamp negativo no `meta.json`/log mas vira 0

```
DEBUG: aligned[0] = -0.85 → clampado para 0.0
```

**Causa**: extrapolação reversa estourou. Já é tratado (clamp em 0)
mas indica que `RATE_MIN_SEC_PER_WORD` está muito baixo OU a primeira
âncora está em < 1s e há várias palavras antes dela.

**Knob**: ver "linhas no começo todas em 00:00.00" acima.

---

### 🔴 Versos de "oh-oh", "la-la-la", "ahhhhh" ficam fora de sincronia

**Causa**: vocalize não-lexical não casa com palavras transcritas pelo
Whisper (que muitas vezes os ignora ou transcreve genericamente).

**Knob**: **nenhum** no LRC align. Esses versos são pontuados por
energia (RMS) no `ws/room.py::_score_vocalize` durante o jogo, não no
alinhamento. Aceite que o timestamp pode ficar ±2s e edite manualmente
no `lyrics.lrc` se for crítico.

---

### 🟡 Match ratio muito alto mas timestamps ainda parecem off

Log do `reinstall_song`:
```
🔎 [LRC ALIGN] Matched 98/100 palavras (98%).
```

Mas os tempos visivelmente errados.

**Causa possível**: Whisper deu word timestamps imprecisos (acontece
em vocais distorcidos ou áudio com forte reverb).

**Knob**: nada no `lrc_align`. Tentar:
- Rodar Demucs antes (se vocal.mp3 vem direto do YouTube, pode estar
  com instrumental sobreposto)
- Mudar modelo do Whisper para `large-v3` (mais lento, mais preciso)
  em `stt_engine.py::STTEngine.__init__`

---

## Fluxo recomendado de troubleshooting

```
1. Rode reinstall_song e abra o lyrics.lrc gerado.

2. Conte os sintomas:
   [ ] Versos colidindo?       → Ajuste 1: min_silence_duration_ms↓
   [ ] Começo em 00:00.00?     → Ajuste 2: RATE_MIN_SEC_PER_WORD↑
   [ ] Refrão duplicado?       → Ajuste 3: WORD_MIN_FUZZ_RATIO↓
   [ ] Whisper alucinando?     → Ajuste 4: VAD.threshold↑

3. Mude UM knob por vez. Rode reinstall. Compare.

4. Se 3+ ajustes não resolverem, pare e edite manualmente o lyrics.lrc.
   Cole no editor da UI (/api/save-lyrics) — ele já normaliza CRLF e
   roda prepare_song.

5. Se o problema é sistêmico (várias músicas), considere mudar o
   default no whisper_params.py.
```

---

## Knobs em ordem de "risco de quebrar outras coisas"

Do mais seguro para o mais perigoso:

1. **`PAUSE_INJECT_MIN_GAP_SEC`** (0.6) — só afeta marcadores de
   pausa, não os timestamps das letras. Pode mexer à vontade.
2. **`WORD_SEARCH_WINDOW`** — aumentar dá mais chance de match,
   custa só um pouco mais de CPU.
3. **`WORD_MIN_FUZZ_RATIO`** — diminuir aumenta falsos positivos de
   match (palavras erradas viram âncoras), mas a interpolação corrige
   na maioria dos casos.
4. **`RATE_MIN/MAX_SEC_PER_WORD`** — afeta SÓ as bordas. Mexer altera
   o início e o fim do LRC, não o meio.
5. **`MIN_FALLBACK_MATCH_PCT` / `MIN_FALLBACK_MATCHES`** — decide se
   cai no fallback linear. Aumentar pode forçar fallback (pior). Não
   recomendado mexer.
6. **`VAD_PARAMETERS.threshold`** — afeta TUDO. Mexer aqui muda quais
   trechos o Whisper sequer transcreve.
7. **`VAD_PARAMETERS.min_silence_duration_ms`** — mais perigoso ainda.
   Afeta como o Whisper agrupa palavras.

Se você nunca mexeu antes, comece pelos 1-4. Os 5-7 são para casos
extremos.

---

## O que NÃO ajustar (e por quê)

| Knob | Por quê deixar em paz |
|---|---|
| `MIN_FALLBACK_MATCHES = 3` | Quando há < 3 matches, a saída do alinhamento é confiavelmente ruim — melhor o fallback linear |
| `NO_LRC_LINE_INTERVAL_SEC = 4.0` | Só usado quando Whisper devolve 0 segmentos — caso patológico |
| `LINEAR_FALLBACK_END_OFFSET = 5.0` | Margem de "fim provável" do canto antes do fade-out |
| `_HALLUCINATION_RE` (a regex em si) | Aceita padrões novos, mas não relaxe os existentes |

---

## Quando aceitar a derrota e editar manualmente

Se depois de 3-4 ajustes o LRC ainda está ruim, provavelmente o
problema NÃO está nos knobs — está num desses:

- **Vocal.mp3 com instrumental sobreposto**: rode Demucs antes. Se já
  rodou, verifique que `vocal.mp3` foi gerado a partir da separação,
  não baixado direto.
- **Áudio com forte reverb / distorção**: Whisper tem limites. Use o
  rascunho gerado pelo `generate_lrc.py` como ponto de partida e
  edite à mão.
- **Letra com versos muito repetidos sem variação** (ex: "na na na na"
  20 vezes): nenhum algoritmo word-matching vai resolver. Edite à mão.

O LRC pode ser editado depois pela UI (`/api/save-lyrics`) — o
`prepare_song` é rodado automaticamente e re-gera `segments.json` com
o alinhamento word-level fino.
