# LRC Alignment Tuning Guide

Quando o `lyrics.lrc` gerado sai com timestamps ruins, este é o playbook. Cada sintoma aponta para 1-2 knobs específicos.

**Arquivos onde os knobs vivem:**
- `karaoke/server/utils/lrc_align.py` — alinhamento letra ↔ Whisper
- `karaoke/server/utils/whisper_params.py` — VAD / transcrição
- `karaoke/server/stt_engine.py` — gate de silêncio do Whisper

Sempre rode `reinstall_song.py` na música depois de mexer num knob — o LRC é regenerado do zero a partir do `meta.json` + `vocal.mp3`.

---

## Como avaliar a qualidade rapidamente

Abra o `.lrc` gerado e procure:

1. **Linhas com `[??:??.??]`** — linhas órfãs (Whisper não casou nenhuma palavra). Esperado para gritos não-lexicais, versos distorcidos, ou letras com pontuação que confunde matching. **Não é bug; é sinalização.** Edite à mão. Ver seção dedicada abaixo.
2. **Sequência de timestamps próximos** (ex: 5+ linhas com gap < 0.3s). Sinal claro de colisão.
3. **Refrão repetido aparecendo só em uma posição**. Cursor não está avançando entre ocorrências.
4. **Linhas "vazadas" pro verso seguinte** (ex: "I beg to dream..." em `[00:45.92]` quando o canto real começa em 00:46.50). Word matching pegou âncora errada.
5. **Muitas linhas órfãs (`[??:??.??]`) em sequência** — pode indicar que o threshold de fuzzy está alto demais ou que o Whisper não está capturando o vocal direito.

Aplique a tabela abaixo conforme o sintoma dominante.

---

## 🟡 Sobre as linhas `[??:??.??]` — regra de ouro

O alinhador **não inventa timestamps**. Se uma linha da letra não tem nenhuma palavra que o Whisper conseguiu ouvir, ela sai como `[??:??.??]<texto>`. Exemplos típicos:

- `(Say: Hey! Cha!)` — grito não-lexical, Whisper transcreve como "hey" ou pula completamente
- `(The representative from California has the floor)` — fala declamada com efeito de telefone (Holiday)
- `Ahhhhhhhhhh` — sustentação vocal, Whisper geralmente ignora
- `[INSTRUMENTAL]` — qualquer marcador artificial

**O que fazer:** abra o `.lrc` no editor da UI (`/api/save-lyrics`), ache as linhas `[??:??.??]`, ouça o áudio e troque o timestamp. O salvamento já dispara o `prepare_song` que re-gera o alinhamento word-level.

**Quando virar problema:** se MUITAS linhas (>20% do total) ficarem órfãs, a culpa não é da regra — é do Whisper. Reduzir `WORD_MIN_FUZZ_RATIO` (80 → 70) pode ajudar antes de aceitar a derrota.

---

## Tabela de sintoma → knob

### 🔴 Versos colidindo (N linhas em 1-2 segundos)

```
[01:46.79]On holiday
[01:47.03]Hear the drum...
[01:47.27]Another protester...
```

**Causa**: Whisper agrupou vários versos num segmento sem pausa suficiente entre eles, e a fração de palavras casadas ficou abaixo do mínimo, caindo no fallback linear.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `whisper_params.py` | `VAD.min_silence_duration_ms` | 700 | **400** (separa versos com pausa curta) |
| `whisper_params.py` | `VAD.threshold` | 0.25 | **0.18** (detecta mais como fala) |
| `lrc_align.py` | `WORD_MIN_FUZZ_RATIO` | 80 | **70** (mais tolerante a erros do Whisper) |

Se ainda colidir: aumentar `WORD_SEARCH_WINDOW` de 40 → 80. Janela maior permite que palavras da letra encontrem matches mesmo quando Whisper transcreveu palavras a mais entre elas.

---

### 🔴 Muitas linhas iniciais com `[??:??.??]`

```
[??:??.??](Say: Hey! Cha!)
[??:??.??]
[??:??.??]Hear the sound of the falling rain
```

**Causa**: as primeiras palavras da letra não casaram com nenhuma palavra do Whisper. Pode ser que o Whisper esteja pulando o intro (VAD restritivo) ou que as primeiras linhas sejam gritos/vocalize.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `whisper_params.py` | `VAD.threshold` | 0.25 | **0.18** |
| `lrc_align.py` | `WORD_MIN_FUZZ_RATIO` | 80 | **70** |

Se persistir: aceitar e editar manualmente — gritos não-lexicais genuinamente não casam.

---

### 🔴 Refrão aparece sempre na mesma posição

```
[01:30.00]I beg to dream...   ← OK
[01:35.00]                     ← interpolado
[01:40.00]                     ← interpolado
[01:42.00]I beg to dream...   ← ❌ Deveria estar em ~02:50
```

**Causa**: cursor forward-only requer que pelo menos algumas palavras **entre** as 2 ocorrências do refrão tenham casado, para que o cursor avance. Se nada casou no meio (verso intermediário com Whisper errado), o cursor fica próximo e a 2ª ocorrência mapeia errado.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `lrc_align.py` | `WORD_MIN_FUZZ_RATIO` | 80 | **70** ou **65** |
| `lrc_align.py` | `WORD_SEARCH_WINDOW` | 40 | **80** ou **120** |

Janela maior + ratio menor = chance maior de ancorar palavras intermediárias e empurrar o cursor para frente.

**Se persistir:** o vocal intermediário entre refrões pode estar suprimido pelo Demucs (instrumental forte). Verifique manualmente que o `vocal.mp3` contém aquele trecho audível.

---

### 🔴 Whisper deixa de transcrever um verso que existe no áudio

Não tem timestamp do verso porque o Whisper nem viu aquele trecho.

**Causa**: VAD considerou silêncio (threshold alto demais) ou o gate de RMS do `stt_engine.transcribe` filtrou.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `whisper_params.py` | `VAD.threshold` | 0.25 | **0.15** |
| `whisper_params.py` | `VAD.speech_pad_ms` | 200 | **400** (mais respiração ao redor da fala) |
| `stt_engine.py` | `rms_threshold` em `transcribe()` | 0.00005 | **0.00001** |

**Risco**: thresholds mais baixos aumentam **alucinações** ("Thanks for watching", "Subscribe to my channel"). O regex `_HALLUCINATION_RE` em `stt_engine.py` filtra os mais comuns, mas se aumentar o ruído, pode passar coisa nova. Olhe os logs.

---

### 🔴 Whisper "alucinando" — frases tipo "Thanks for watching"

**Causa**: VAD pegou silêncio ou ruído ambiente como fala.

**Knobs:**
| Arquivo | Constante | Default | Tentar |
|---|---|---|---|
| `whisper_params.py` | `VAD.threshold` | 0.25 | **0.35** (mais restritivo) |
| `stt_engine.py` | `rms_threshold` | 0.00005 | **0.0001** |
| `stt_engine.py` | `_HALLUCINATION_RE` | regex EN/PT | adicione padrões novos |

Se aparecer um padrão novo de alucinação, adicione no regex em `stt_engine.py`. Padrões comuns extras:
```
"like and subscribe"
"see you next time"
"video patrocinado"
"obrigado por assistir"
```

---

### 🔴 Versos de "oh-oh", "la-la-la", "ahhhhh" saem com `[??:??.??]`

**Causa**: vocalize não-lexical não casa com palavras do Whisper (que muitas vezes os ignora ou transcreve genericamente). Saem como órfãs — comportamento esperado.

**Knob**: **nenhum** no LRC align. Edite manualmente pelo `/api/save-lyrics`. Durante o jogo esses versos são pontuados por energia (RMS) no `ws/room.py::_score_vocalize`, não pelo texto, então ter o timestamp correto basta.

---

### 🟡 Match ratio muito alto mas timestamps ainda parecem off

Log do `reinstall_song`:
```
🔎 [LRC ALIGN] Matched 98/100 palavras (98%).
```

Mas os tempos visivelmente errados.

**Causa possível**: Whisper deu word timestamps imprecisos (acontece em vocais distorcidos ou áudio com forte reverb).

**Knob**: nada no `lrc_align`. Tentar:
- Rodar Demucs antes (se vocal.mp3 vem direto do YouTube, pode estar com instrumental sobreposto)
- Mudar modelo do Whisper para `large-v3` (mais lento, mais preciso) em `stt_engine.py::STTEngine.__init__`

---

## Fluxo recomendado de troubleshooting

```
1. Rode reinstall_song e abra o lyrics.lrc gerado.

2. Conte os sintomas:
   [ ] Linhas com [??:??.??]?  → Editar manualmente (regra: não inventar tempo)
   [ ] Versos colidindo?       → Ajuste 1: min_silence_duration_ms↓
   [ ] Muitas órfãs no início? → Ajuste 2: VAD.threshold↓ ou WORD_MIN_FUZZ_RATIO↓
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

1. **`PAUSE_INJECT_MIN_GAP_SEC`** (0.6) — só afeta marcadores de pausa, não os timestamps das letras. Pode mexer à vontade.
2. **`WORD_SEARCH_WINDOW`** (40) — aumentar dá mais chance de match, custa só um pouco mais de CPU.
3. **`WORD_MIN_FUZZ_RATIO`** (80) — diminuir reduz órfãs mas aumenta risco de match falso positivo (palavra errada vira âncora). Tradeoff: 70-75 funciona bem para Whisper com transcrição imperfeita; 85+ só pra letras muito limpas.
4. **`MIN_FALLBACK_MATCH_PCT` / `MIN_FALLBACK_MATCHES`** — decide se cai no fallback linear (toda a letra distribuída uniformemente). Não recomendado mexer.
5. **`VAD_PARAMETERS.threshold`** — afeta TUDO. Mexer aqui muda quais trechos o Whisper sequer transcreve.
6. **`VAD_PARAMETERS.min_silence_duration_ms`** — mais perigoso ainda. Afeta como o Whisper agrupa palavras.

Se você nunca mexeu antes, comece pelos 1-3. Os 4-6 são para casos extremos.

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

Se depois de 3-4 ajustes o LRC ainda está ruim, provavelmente o problema NÃO está nos knobs — está num desses:

- **Vocal.mp3 com instrumental sobreposto**: rode Demucs antes. Se já rodou, verifique que `vocal.mp3` foi gerado a partir da separação, não baixado direto.
- **Áudio com forte reverb / distorção**: Whisper tem limites. Use o rascunho gerado pelo `generate_lrc.py` como ponto de partida e edite à mão.
- **Letra com versos muito repetidos sem variação** (ex: "na na na na" 20 vezes): nenhum algoritmo word-matching vai resolver. Edite à mão.

O LRC pode ser editado depois pela UI (`/api/save-lyrics`) — o `prepare_song` é rodado automaticamente e re-gera `segments.json` com o alinhamento word-level fino.
