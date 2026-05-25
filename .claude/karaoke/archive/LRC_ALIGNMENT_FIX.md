# 🗄️ Archived LRC Alignment Word-Level Refactor Notes

> [!NOTE]
> **HISTÓRICO DA CORREÇÃO DE ALINHAMENTO LRC / ARCHIVED ALIGNMENT FIX HISTORY**
> Este documento registra as notas de onboarding referentes à transição do matching por linhas para o matching por palavras (SequenceMatcher) a fim de corrigir o bug de compressão temporal da música Holiday.
> Para orientações ativas sobre como resolver problemas de alinhamento, consulte:
> - [LRC Alignment Tuning Guide](../guides/LRC_ALIGNMENT_TUNING.md)

---

# LRC Alignment — Word-Level Refactor

Documento de onboarding para a mudança feita no algoritmo de geração automática do `lyrics.lrc`. Resume **o que mudou, por quê, e como validar** o comportamento.

Branch: `main` · Commits relevantes: ver `git log` a partir desta data.

---

## TL;DR

Antes:
```
[01:46.79]On holiday
[01:46.91]Hear the drum pounding out of time
[01:47.03]Another protester has crossed the line (hey!)
[01:47.15]To find the money's on the other side
...
```
10 versos consecutivos achatados em ~1s. Bug do Holiday do Green Day.

Depois: cada verso recebe o timestamp da primeira palavra que casou com a transcrição do Whisper. Timestamps distribuídos pelo áudio inteiro.

---

## Causa raiz da regressão

O algoritmo antigo (`server/utils/lrc_align.py`, versão pré-fix) fazia match no nível de **linha vs `segment` do Whisper**:

```python
for j in range(last_j, min(m, last_j + WHISPER_SEARCH_WINDOW)):
    ratio = _substring_match_ratio(ref_lines[i], whisper_lines[j]["text"])
    if ratio > best_ratio: ...
if best_j != -1: aligned[i] = whisper_lines[best_j]["start"]
```

Quando o **VAD do faster-whisper** estava configurado com `min_silence_duration_ms=2000`, versos consecutivos separados por menos de 2s de silêncio eram **mesclados num único `Segment`**. Resultado: N linhas de referência casavam todas com o mesmo `j`, e o passo 2 ("se múltiplas refs no mesmo segment, distribui linearmente") gerava N timestamps consecutivos em frações de segundo:

```python
for idx, ref_idx in enumerate(indices):
    aligned[ref_idx] = seg_start + idx * (duration / len(indices))
```

Cenário Holiday: 10 linhas em segment de 1.2s → 0.12s entre cada.

## A correção

Três mudanças complementares num só refactor:

### 1. Matching por palavra com `difflib.SequenceMatcher`

`server/utils/lrc_align.py` reescrito. Em vez de `linha ↔ segment`, agora:

1. Achata **todas as palavras** das ref_lines em um array com mapa `palavra → linha`.
2. Achata `segments[].words[]` do Whisper em outro array (já vem com timestamps por palavra porque `word_timestamps=True`).
3. `SequenceMatcher(a=ref_tokens, b=whisper_tokens).get_matching_blocks()` acha a maior subsequência comum.
4. Para cada par casado: o `start`/`end` do Whisper vira âncora da palavra de referência.
5. Palavras não-casadas interpolam linearmente entre vizinhas casadas.
6. Timestamp de cada **linha** = timestamp da **primeira palavra** dela.

**Por que SequenceMatcher resolve o problema do Holiday:** ele lida naturalmente com refrões repetidos e versos colados — palavras casadas mantêm a ordem original do áudio, e a interpolação distribui o resto proporcionalmente. Não há mais "10 linhas mapeadas no mesmo objeto".

**API pública preservada:**
```python
align_plain_lyrics(plain_lyrics, whisper_segments, title, artist, total_vocal_duration_sec)
    -> (lrc_text: str, fallback_used: bool)
```

### 2. Parâmetros VAD unificados

Novo módulo `server/utils/whisper_params.py`:

```python
VAD_PARAMETERS = {
    "threshold": 0.25,
    "min_silence_duration_ms": 700,   # era 2000 em reinstall
    "speech_pad_ms": 200,             # era 600 em reinstall
}
TRANSCRIBE_KWARGS = {
    "beam_size": 5,
    "vad_filter": True,
    "vad_parameters": VAD_PARAMETERS,
    "condition_on_previous_text": False,
    "word_timestamps": True,
}
```

`server/routes/upload.py` e `tools/reinstall_song.py` agora chamam `model.transcribe(... **TRANSCRIBE_KWARGS)`. Antes divergiam: upload usava defaults do faster-whisper (`threshold=0.5`, mais restritivo) e reinstall usava `min_silence_duration_ms=2000` agressivo (mesclava versos). Isso explicava a observação **"baixar a primeira vez tem resultado melhor"** — eram dois algoritmos diferentes.

### 3. `initial_prompt` no reinstall

`tools/reinstall_song.py` agora passa `initial_prompt=plain_lyrics` para o Whisper quando há letra de referência. Ajuda o modelo com termos raros ("Sieg Heil", "Gasman", nomes próprios) que ele não transcreveria sozinho. Já era usado em `prepare_song.py` por segmento; agora também na varredura global.

---

## Como validar

### Smoke tests inclusos

Os testes ficam inline (rodados durante o commit, não vão pro repo) mas ficam de referência:

```python
import sys; sys.path.insert(0, 'server')
from utils.lrc_align import align_plain_lyrics

class W:
    def __init__(self, word, start, end):
        self.word, self.start, self.end = word, start, end
class Seg:
    def __init__(self, words): self.words = words

# Cenário Holiday-like
segs = [Seg([
    W('hear', 20.0, 20.4), W('the', 20.4, 20.5), W('sound', 20.5, 21.0),
    W('coming', 23.0, 23.5), W('down', 23.5, 24.0),
    W('the', 26.0, 26.2), W('shame', 26.2, 26.7),
])]
ref = "Hear the sound of falling\nComing down like flame\nThe shame of ones"
text, _ = align_plain_lyrics(ref, segs, 'T', 'A', 60.0)
# Antes: as 3 linhas colidiam em ~20s.
# Agora: 20.00, 23.00, 26.00 — distribuídas pelos timestamps reais.
```

### Validação ponta-a-ponta

Para testar com o Holiday real:

```bash
cd karaoke/server
python main.py
# Em outro shell:
# 1. Apague songs/holiday-green-day se existir
# 2. POST /api/upload-song com YouTube vocal+backing e plain_lyrics
# 3. Inspecionar songs/holiday-green-day/lyrics.lrc
```

Esperado: as linhas do segundo verso "Hear the drum pounding..." em torno de 01:25-01:35 (timestamps reais do áudio), não mais 01:46.79 → 01:47.87 colapsadas.

---

## O que pode dar errado / casos limites

1. **Letra de referência muito diferente da letra real.** Se o usuário colar a letra errada, `SequenceMatcher` não vai achar matches. Cai no fallback linear (mesmo critério da versão antiga: matched < `max(3, 15% das linhas)`). Comportamento idêntico ao anterior.

2. **Pronúncia divergente.** `_normalize_word` faz lowercase + strip pontuação. Variações fonéticas (`"gonna"` vs `"going to"`) ainda podem não casar. Aceitável — `SequenceMatcher` é tolerante a gaps, e a interpolação cobre.

3. **Versos só com vocalize ("oh-oh", "la-la-la").** O Whisper às vezes transcreve como `"oh oh oh"` ou ignora; se não casar com a letra, vira interpolação. OK.

4. **Vocais com muito grito/distorção** (Holiday tem isso). O VAD com `threshold=0.25` agora é mais sensível, deve detectar mais como fala. Se ainda assim pular fala, o usuário pode rodar `reinstall_song.py` manualmente — o fluxo é idempotente.

---

## Arquivos tocados

```
karaoke/server/utils/whisper_params.py   NEW  (32 linhas)
karaoke/server/utils/lrc_align.py        REWRITE  (198 → 305 linhas)
karaoke/server/routes/upload.py          patch (VAD via TRANSCRIBE_KWARGS)
karaoke/tools/reinstall_song.py          patch (VAD + initial_prompt)
karaoke/docs/LRC_ALIGNMENT_FIX.md        NEW  (este arquivo)
```

Sem mudanças nos modelos persistidos (`meta.json`, `segments.json`, `lyrics.lrc`). Sem mudanças no protocolo WebSocket. Frontend intocado.

---

## TODOs explicitamente NÃO feitos (e por quê)

- **Flag `vocal_is_isolated` no `meta.json`** (apontado no diagnóstico do ponto 5). Adicionaria superfície de UI nova; conservador deixar pra uma issue separada. O sintoma "demucs roda em vocal isolado" continua existindo quando o usuário fornece só o `youtube_vocal_url` sem backing — mas o impacto é menor do que o bug do alinhamento.
- **Word-level merge de fragmentos vocais** (`"oh"`, `"ah"`) no align. Já existe `merge_vocal_fragments` em `score_engine.py` para outra finalidade; reaproveitar exigiria refactor extra. Deixado pra depois.
- **Reordenar Demucs + Whisper paralelo.** Ambos competem por GPU; não vale a complexidade.

Esses pontos estão também no `BACKEND_REFACTOR_NOTES.md` como TODOs gerais.
