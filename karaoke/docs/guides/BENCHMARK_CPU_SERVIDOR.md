# Karaoke AI em CPU — benchmark no marcelo-server

Data: 2026-10-12 (02:11–06:00 UTC). Código medido: `ad584e6`, sem alterações.
Scripts, saídas brutas (JSON/logs) e o original deste relatório ficaram no servidor, em `~/karaoke-bench/` (fora do git).

## Resumo

- **Recomendação: `small`, int8, 10 threads** (`KARAOKE_WHISPER_MODEL=small KARAOKE_WHISPER_DEVICE=cpu OMP_NUM_THREADS=10`, já funciona sem mexer no código).
- **Acerto praticamente igual ao de hoje**: MAE 18,8 do `small` contra 18,2 do `large-v3-turbo` (208 versos com gabarito); o `medium` dá 19,2.
- **Meta de 3 s: só parcialmente atingida.** 1 cantor, verso isolado: p50 1,9 s, **p95 3,7 s** (não passa no p95). Na GPU: p50 0,41 s, p95 0,64 s.
- **Música inteira é o problema**: o servidor transcreve um verso por vez (lock global). Em músicas de versos curtos em sequência a fila acumula — até 24 s de atraso com 1 cantor na My Iron Lung — e **com 2 cantores no mesmo verso a fila cresce sem parar** (1–2 min) e as últimas notas se perdem no timeout de 10 s do fim da música.
- `medium` e `large-v3-turbo` são inviáveis aqui (p50 4,7 s e 6,7 s por verso no melhor caso).
- **Adicionar música durante a partida: dá**, com custo. Demucs leva 2 min sozinho (música de 4,6 min), 3 min com a nota rodando; nesse período a nota fica ~65% mais lenta (p50 1,95 → 3,2 s). RAM sobra (mínimo de 9 GB livres).

## Máquina e ambiente

| | |
|---|---|
| CPU | Intel Xeon E5-2630 v4 @ 2,20 GHz, 10 núcleos / 20 threads, AVX2 |
| RAM | 15,5 GiB + 4 GiB swap |
| GPU | nenhuma (`nvidia-smi` ausente) |
| SO | Linux 6.8.0-142, Python 3.12.3 |
| torch / torchaudio | 2.6.0+cpu / 2.6.0+cpu |
| faster-whisper / ctranslate2 | 1.2.1 / 4.7.2 |
| demucs | 4.0.1 |
| `get_supported_compute_types("cpu")` | float32, int16, int8, int8_float32 |
| `nproc` | 20 |

**Carga de fundo (outros serviços, não foram parados):** no início, 3,8–5,8 GiB usados, ~11 GiB disponíveis, CPU 98% ociosa no instante medido, mas load average 3,6 (algo rodou pouco antes). Todos os números abaixo foram medidos com esses serviços no ar. Detalhes em `background_load.txt`.

**Testes:** `pytest tests --ignore=tests/ui` → 354 passaram, 1 pulado, 5 erros. Os 5 erros são todos de `tests/test_escolta_vagalumes.py`, que precisa do `vocal.mp3` dessa música (não está no git) e de CUDA — o README já avisa. Nenhuma falha real. (`pytest.txt`)

## Como foi medido

- `bench_latency.py`: recorta as janelas exatamente como `tools/replay_recording.py` (`segment_window`, `covered_mask`, `needs_whisper`) e chama o **próprio `STTEngine.transcribe` do servidor** (beam 5, VAD, word_timestamps, letra como dica + segunda passada sem dica quando a confiança é baixa) e depois `score_words`. Só o `WhisperModel` é criado à parte, com `cpu_threads`.
- 283 janelas das 6 partidas iriam ao Whisper; por combinação foram medidas 40 espalhadas pelas 6 partidas (duração mediana 3,75 s) + 1 de aquecimento descartada.
- **2 cantores**: o servidor usa **um modelo compartilhado** e serializa com `queue_manager.whisper_lock` (asyncio.Lock + `to_thread`) — ver `ws/room.py:254`. Imitado com 2 threads e um `threading.Lock`; 12 pares de versos disparados juntos, medido o tempo até a nota do 2º. Extra: variante sem lock com `num_workers=2` (para avaliar mudança de código).
- `bench_queue.py`: transcreve **todos** os versos de duas músicas e simula a fila do servidor (verso despachado no fim da janela + 0,6 s de folga, um por vez).
- Acerto: `tools/replay_recording.py --device cpu --model <m>` sem alteração, com `OMP_NUM_THREADS=10` só para acelerar (ver abaixo).

## 1. Tempo por verso — 1 cantor (s)

| modelo | threads | p50 | p95 | máx | tempo/duração da janela (p50) |
|---|---|---|---|---|---|
| base | 4 | 1,68 | 13,9 | 17,4 | 0,50 |
| base | 10 | **1,39** | 14,3 | 16,8 | 0,38 |
| small | 4 | 2,65 | 4,90 | 5,68 | 0,73 |
| **small** | **10** | **1,92** | **3,68** | 4,22 | 0,52 |
| small | 20 | 3,26 | 5,52 | 11,0 | 0,91 |
| medium | 4 | 8,47 | 16,2 | 16,4 | 2,39 |
| medium | 10 | 4,74 | 8,89 | 9,18 | 1,32 |
| medium | 20 | 8,45 | 14,9 | 16,1 | 2,35 |
| large-v3-turbo | 4 | 12,5 | 24,9 | 29,6 | 3,33 |
| large-v3-turbo | 10 | 6,75 | 13,6 | 17,6 | 1,81 |
| large-v3-turbo | 20 | 10,1 | 13,1 | 23,6 | 2,71 |
| *GPU RTX 4070 (das gravações)* | | *0,41* | *0,64* | | |

compute_type int8 em tudo (disponível). O turbo não passou de 10 s de p50 com 10 threads, então a matriz dele foi completada.

**Observações:**
- **10 threads é o ótimo.** 20 usa hyperthreading e piora tudo (as threads extras disputam as mesmas unidades AVX).
- **Há um piso fixo por passada** (~1,85 s no `small`, 10 threads), igual para janela de 2 s ou de 16 s: o Whisper sempre completa o áudio até 30 s, e o encoder sozinho custa **1,49 s** desses ~1,9 s (`probe_breakdown_small.log`). Beam 5 → 1 quase não muda a mediana (1,88 → 1,85 s).
- **Verso com segunda passada (sem dica) custa o dobro** (~3,6 s no `small`): é o que forma o p95 do `small`.
- **Os máximos altos vêm de loop do Whisper**: no aoi-koi#18 ele repetiu "と、と、と…" até o limite de tokens e, com o fallback de temperatura do faster-whisper (0 → 1,0), levou **24 s no `small`** (`probe_small.log`). Com `temperature=0` cai para 16,6 s e com `max_new_tokens=64` para 5,2 s (`probe_tokens.log`). O `base` entra em loop com muito mais frequência (p95 ~14 s).

## 2. Tempo até a nota do 2º cantor — 2 cantores no mesmo verso (s)

| modelo | threads | lock (servidor atual) p50 | p95 | máx | sem lock, 2 workers × threads/2: p50 | p95 |
|---|---|---|---|---|---|---|
| base | 10 | 3,48 | 11,5 | 11,8 | – | – |
| small | 4 | 5,38 | 20,9 | 34,9 | 5,07 | 38,3 |
| **small** | **10** | **3,96** | 24,3 | 45,6 | **3,03** | 15,0 |
| small | 20 | 6,88 | 45,9 | 88,8 | 3,37 | 21,2 |
| medium | 10 | 9,52 | 17,8 | 18,4 | 8,61 | 16,1 |
| large-v3-turbo | 10 | 13,6 | 25,8 | 27,9 | – | – |

Com o lock, o 2º espera o 1º: na mediana, o dobro do tempo de 1 verso. O p95/máximo de 12 pares é dominado por um par que contém o verso com loop (aoi-koi#18). Dois workers sem lock ajudam pouco (o encoder já usa todos os núcleos).

## 3. A música inteira (fila) — `small` e `medium`, 10 threads

Atraso até a nota (despacho → nota), simulando a fila do servidor com o tempo medido de cada verso:

| música | modelo | versos | 1 cantor p50 / p95 / máx | versos > 3 s | 2 cantores (nota do 2º) p50 / p95 / máx | fim da música |
|---|---|---|---|---|---|---|
| Rap do Gaara (versos a cada ~2–3 s) | small | 66 | 2,1 / 5,7 / 8,4 | 12 | 50 / 91 / 95 | 1 cantor ok; **2 cantores: notas finais perdidas** |
| My Iron Lung (versos curtos seguidos) | small | 72 | 4,2 / 20,4 / 26,7 | 43 | 34 / 112 / 127 | **perde notas finais já com 1 cantor** |
| Rap do Gaara | medium | 66 | 72 / 220 / 233 | 66 | 239 / 620 / 655 | inviável |
| My Iron Lung | medium | 72 | 80 / 174 / 197 | 72 | 297 / 595 / 649 | inviável |

"Perdidas" = a última nota sai mais de 10 s depois do fim da música (`PENDING_TASKS_TIMEOUT_SEC`): o `game_over` sai sem ela. No modo de revezar versos (1 cantor por verso) o caso de 2 cantores se comporta como o de 1.

## 4. Acerto da nota (MAE vs gabarito; menor = melhor)

| partida | versos c/ gabarito | base | small | medium | large-v3-turbo |
|---|---|---|---|---|---|
| 505 (Arctic Monkeys) | 1 | 28,6 | 42,9 | 42,9 | 28,6 |
| Teen Idle (Marina) | 1 | 6,5 | 12,1 | 21,5 | 7,0 |
| Aoi Koi (japonês) | 33 | 44,8 | **23,7** | **15,7** | 27,8 |
| Rap do Gaara | 66 | 19,0 | 12,0 | 15,2 | **11,0** |
| Último Romance | 35 | 19,4 | 10,6 | 11,2 | **9,3** |
| My Iron Lung | 72 | 29,6 | 26,6 | 28,1 | **24,8** |
| **Ponderado (208 versos)** | | **26,8** | **18,8** | **19,2** | **18,2** |
| Nota final média (gravada na GPU: 84,8) | | 74,9 | 84,1 | 85,3 | 84,2 |

- `small` perde **0,6 ponto de MAE** em relação ao `large-v3-turbo` — dentro do ruído de 208 versos. No japonês ele é até melhor.
- As duas primeiras partidas têm só 1 verso anotado cada: o MAE delas é praticamente aleatório e conta quase nada no ponderado.
- `base` é claramente pior (+8,6), apesar de ser o mais rápido.
- Os limiares de confiança foram calibrados no `medium`; não houve sinal de que precisem de ajuste para o `small`.
- O turbo em CPU int8 deu final 84,2, praticamente igual ao gravado na GPU em float16 (84,8), então ele serve de referência.

## 5. Demucs (separação) — `htdemucs --two-stems vocals`, música de 4 min 36 s

| | tempo | CPU | pico de RAM |
|---|---|---|---|
| sozinho | **2 min 00 s** | 825% | 1,96 GB |
| junto com a nota ao vivo (`small`, 10 threads, laço contínuo) | **3 min 03 s** | 813% | 1,97 GB |

Nota ao vivo (`small`, 10 threads) no mesmo laço:

| | n | p50 | p95 | máx |
|---|---|---|---|---|
| antes do Demucs | 39 | 1,95 | 3,66 | 4,17 |
| **durante o Demucs** | 52 | **3,22** | **6,08** | 8,02 |
| depois | 100 | 1,98 | 3,75 | 4,81 |

Menor RAM disponível no teste: **9,0 GB** — a trava de 1 GB não chegou a disparar.

## 6. RAM de pico por modelo (processo do replay, `maxrss`)

base 0,9 GB · small 1,6 GB · medium 3,0 GB · large-v3-turbo 1,9 GB · Demucs +2,0 GB. Com os ~4–6 GB dos outros serviços, sobra folga para qualquer combinação.

## Recomendação

1. **Modelo `small`, int8, 10 threads.** O acerto é o mesmo do `large-v3-turbo` e é o único que chega perto da meta. Já funciona hoje sem mudar código:
   ```
   KARAOKE_WHISPER_MODEL=small KARAOKE_WHISPER_DEVICE=cpu OMP_NUM_THREADS=10 ./venv/bin/python server/main.py
   ```
   O ctranslate2 lê `OMP_NUM_THREADS` quando `cpu_threads` não é passado (medido: p50 2,68 s → 1,87 s no `STTEngine` original).
2. **A meta de p95 ≤ 3 s não foi atingida**: 3,7 s com 1 cantor e ~4 s na mediana para o 2º cantor. Com as mudanças de código abaixo, ela fica ao alcance para 1 cantor.
3. **Uso realista nesta máquina, como está hoje:** 1 cantor por verso (solo ou revezando) em músicas de ritmo normal. Dueto cantando os mesmos versos e músicas de versos muito curtos e seguidos acumulam fila e perdem notas no fim.
4. **Adicionar música durante a partida: pode.** Por 3 min a nota fica ~65% mais lenta (p50 ~3,2 s). Melhor ainda se a separação usar menos threads (ver abaixo).

## O que mudar no código para rodar bem aqui (só descrito; repo não foi alterado)

Por ordem de impacto:

1. **`cpu_threads` configurável**: `KARAOKE_WHISPER_THREADS` no `STTEngine._load` → `WhisperModel(..., cpu_threads=int(env or 0))`. O `OMP_NUM_THREADS` já resolve, mas explícito é melhor e aparece na gravação (`versions`).
2. **Cortar o loop do Whisper** em `_transcribe_once`: `max_new_tokens` proporcional ao verso (por exemplo `min(96, 4 × palavras esperadas + 16)`) e `temperature=[0.0, 0.4]` ou só `0.0` em vez do fallback padrão até 1,0. Isso tira os casos de 16–30 s (o verso com loop seria descartado de qualquer forma). Também ajuda na GPU.
3. **Não re-encodar na segunda passada**: o encoder é ~80% do custo e hoje roda 2× quando a dica é recusada. Encodar uma vez (`model.encode`) e decodificar duas vezes, com e sem prompt, via `model.model.generate(encoder_output, ...)`. Isso corta ~40% do tempo desses versos, que são o p95.
4. **2 cantores em lote**: em vez do lock por verso, juntar as janelas pendentes do mesmo verso e encodar em batch (o ctranslate2 aceita batch no `encode`/`generate`; o faster-whisper tem `BatchedInferencePipeline`). Duas janelas em batch custam bem menos que 2× uma.
5. **Fila que não estoura**: se a fila do Whisper passar de N versos (por exemplo 3), pontuar o verso pendente mais antigo sem Whisper (`score_whisper_free`/pitch) ou descartar, em vez de atrasar tudo; e/ou ligar `PENDING_TASKS_TIMEOUT_SEC` ao tamanho da fila.
6. **Demucs com menos threads durante uma partida**: `torch.set_num_threads(4–6)` no processo de separação quando houver sala ativa, deixando núcleos para o Whisper (a separação fica mais lenta, mas a nota não sofre tanto). Rodar o Demucs com `nice`.
7. Opcional: `DEFAULT_COMPUTE`/`DEFAULT_WHISPER_MODEL` dependentes do device (`small` na CPU, `large-v3-turbo` na GPU) para que `device=auto` sem GPU já caia na configuração certa.

## Erros, passos pulados e decisões

- **torch**: o `pip install --force-reinstall torch torchaudio --index-url .../whl/cpu` sem versão instalou torch 2.14.1 e torchaudio 2.11, incompatíveis entre si e diferentes do `2.6.0` fixado no requirements. Reinstalei `torch==2.6.0 torchaudio==2.6.0` CPU (`--no-deps`), voltei o `sympy` para 1.13.1 (`pip check` limpo) e removi as rodas `nvidia-*` que o requirements (índice cu124) tinha trazido. venv: 2,2 GB.
- Sem sudo (`sudo -n` pede senha). Não foi necessário: `ffmpeg` já estava instalado.
- `pytest` não está no requirements: instalado no venv.
- Amostragem: 40 versos por combinação (+12 pares), não todos os 283, para caber a matriz em tempo razoável. O passo 3 e a fila usam todos os versos.
- **Extras não pedidos**: modelo `base` (latência e acerto), variante de 2 cantores sem lock com 2 workers, simulação da fila numa música inteira (`bench_queue.py`), decomposição encoder/decoder e testes de `temperature`/`max_new_tokens` (`probe_*.py`).
- O replay do passo 3 rodou com `OMP_NUM_THREADS=10` para levar 10–36 min por modelo, em vez de ~2,5×. Isso não muda a transcrição de forma relevante (int8 com outro nº de threads pode variar no último dígito).
- RAM "após carga" do `bench_latency` só vale para a primeira combinação de cada processo (o arquivo do modelo já fica em cache depois). Para RAM por modelo, usar o `maxrss` do replay (seção 6).
- O gabarito das partidas 505 e Teen Idle tem 1 verso cada; elas pesam pouco no MAE.

## Arquivos

`bench_latency.py`, `bench_queue.py`, `run_rest.sh`, `probe_pairs.py`, `probe_breakdown.py`, `probe_tokens.py`, `probe_omp.py` · resultados `lat_*.json`, `queue_*.json`, `replay_*.json/.log`, `demucs_*.time`, `lat_with_demucs.json`, `versions.txt`, `pytest.txt`, `background_load.txt` · separação em `demucs_out/`.
