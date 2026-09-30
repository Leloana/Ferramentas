# Avaliação de STT para o score ao vivo (2026-09-29)

Pergunta: trocar o Whisper `large-v3-turbo` por um modelo mais novo, pensando também em outras
línguas (japonês)? Resposta: **não, por enquanto**. O Whisper com a letra como dica e a
segunda opinião sem dica (`stt_engine.PROMPT_TRUST_MIN_PROB`) ganhou do Qwen3-ASR nos nossos
dados. Para japonês, o gargalo é o pipeline, não o modelo (ver no fim).

## Como foi medido

Mesmas janelas de verso (`mic_stream.segment_window`) de 3 partidas reais gravadas (189 versos,
PT e EN), mesmo `segment_scoring`, só trocando o reconhecedor. Duas réguas:

- **canto certo**: nota final e o gabarito de `tests/unit/test_recorded_sessions.py`;
- **letra errada**: 120 pares com o áudio de um verso e a letra de outro
  (`tests/fixtures/recorded_sessions/wrong_lyrics_pairs.json`) — tem que dar nota baixa.

| Reconhecedor | Zé / Wolf / Geni | Falhas gabarito | Letra errada média / máx | Latência/verso | VRAM |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Whisper turbo + dica + segunda opinião** | 94,2 / 72,0 / 81,4 | **5** | **5,5 / 51** | **0,25 s** | ~3 GB |
| Qwen3-ASR 1.7B + letra como `context` | 96,8 / 74,3 / 82,3 | 9 | 9,7 / **100** | 0,94 s | 6,0 GB |
| Qwen3-ASR 1.7B sem contexto | 88,0 / 55,3 / 75,1 | 14 | 4,5 / 51 | 0,94 s | 6,0 GB |
| Qwen3-ASR 0.6B sem contexto | 86,8 / 50,1 / 70,6 | 20 | 4,6 / 51 | 0,85 s | 3,5 GB |

(Qwen via `qwen-asr` 0.0.6, backend transformers, bf16, RTX 4070; vLLM seria mais rápido.)

## Por que o Qwen3-ASR perdeu aqui, apesar dos benchmarks

- **Sem contexto** ele erra o que o Whisper acerta com a dica: "Take the Democrat" (credit
  cards), "Ela não possui de bondade" (é um poço). No karaokê a letra esperada é conhecida;
  jogar isso fora custa caro. Benchmarks de canto (M4Singer etc.) e o SingZ (WER 0,162 × 0,211)
  medem transcrição **sem** letra — outra tarefa.
- **Com contexto** ele copia a letra quando o cantor murmura (Geni 80 cantarolado → 100; Wolf
  44/45, trecho que o cantor não sabia → 95/100) e **não expõe confiança por palavra**, então
  não dá para aplicar a segunda opinião que protege o Whisper.

## O que vale reaproveitar

- **Qwen3-ForcedAligner-0.6B**: alinhador de 11 línguas (inclui ja, pt, en, es), AAS 27,8 ms no
  relatório (NFA 88,6 ms). Candidato para a **preparação da música** (hoje MMS_FA), sobretudo
  japonês. Não testado ainda contra o MMS_FA nas nossas músicas.
- Se um dia o score precisar funcionar **sem** letra, o Qwen3-ASR sem contexto é a escolha.

## Japonês: o que falta no pipeline (independe do modelo)

O Whisper turbo já reconhece japonês (CER 0,184 × 0,140 do Qwen 1.7B em fala natural,
benchmark Neosophie 2026-05). Quebra hoje:

1. `lrc_pro.parse_and_normalize_lyrics` separa palavras por espaço (japonês não tem) e passa
   por `unidecode` (kanji vira pinyin chinês) → precisa tokenizar (fugashi/nagisa) e converter
   para leitura (kana/romaji) antes do MMS_FA — ou alinhar com o Qwen3-ForcedAligner.
2. `score_engine` compara palavras: o STT pode escrever a mesma palavra em kanji ou kana →
   comparar pela leitura (kana), tokenizando esperado e transcrito do mesmo jeito.
3. Seletor de idioma da música (`index.html`) sem `ja`.

Fontes: Qwen3-ASR (github.com/QwenLM/Qwen3-ASR, arXiv 2601.21337), benchmark japonês
Neosophie (neosophie.com/en/blog/20260226-japanese-asr-benchmark), SingZ PRs #48/#51.
