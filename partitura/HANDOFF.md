# Handoff — Partitura (estado em 2026-11-10)

Música com voz → partitura de piano com a letra embaixo das notas (PDF, MusicXML, MIDI,
prévia em áudio), três níveis, interface web. **Sempre algoritmo**: modelos de áudio
(Demucs, torchcrepe, Whisper, MMS_FA do karaokê, Pop2Piano, AMT-APC) + regras musicais.
**Nada de LLM na geração nem na validação** (pedido do usuário).

Leia nesta ordem: este arquivo → `README.md` (uso e opções) → `PROXIMA_ETAPA.md` (plano por
frentes) → `METRICAS_VALIDACAO.md` (como medir) → `HISTORICO.md` (crônica detalhada, §1–30).

## 1. Onde roda

- **Windows (máquina principal)**: biblioteca `saida/` (8 músicas × versões × níveis), GPU
  RTX 4070 12 GB, venv com torch/CUDA, FluidSynth + SoundFont Steinway. Tudo que precisa de
  modelo (separar, transcrever, regenerar, medir fidelidade) roda lá.
- **Linux (esta máquina)**: sem GPU e sem a biblioteca (`saida/`, `trabalho/`, `entrada/`
  não existem aqui). Desenvolvimento e testes com dados montados (Ode à Alegria, domínio
  público, em `test_introducao.ode()`) e os 5 recortes de `exemplos/`. O karaokê aqui só
  tem os `meta.json` (sem áudio).
- Ambiente de teste no Linux: venv no scratchpad da sessão (some ao reiniciar). Pacotes
  usados: music21 numpy pretty_midi verovio soundfile librosa pyphen mir_eval unidecode
  rapidfuzz metaphone fugashi unidic-lite pykakasi fastapi uvicorn pillow; `tinysoundfont`
  com `--no-deps` (a dependência pyaudio não compila) + soundfont
  `/snap/vlc/*/usr/share/sounds/sf2/TimGM6mb.sf2` pras páginas de comparação.
- Suíte: `python -m unittest test_*` (96 testes em 2026-11-10).

## 2. Pipeline (ordem real em `gerar.py`)

1. Separação (`separar`, Demucs `htdemucs`; `--separador htdemucs_6s` também guitarra e piano)
   ou `--do-karaoke` (voz/acompanhamento do karaokê) ou `--reusar-cache` (pula 1–5).
2. Batidas e tempo 1 (`batidas`, `fase_compasso`) → `Grade`.
3. Melodia (`melodia`, torchcrepe) + quadros do detector no diagnóstico (pra `palavras_sem_nota`).
4. Acordes (`acordes`, croma + Viterbi; com 6 faixas usa guitarra + piano).
5. Letra: Whisper → alinhamento forçado do karaokê (`alinhamento.py`, MMS_FA) quando há
   letra oficial (LRCLIB) → `cache/transcricao.json`.
6. Por nível (`gerar_nivel`): proteção da melodia (`protecao_melodia.py`) → palavra sem nota
   (`palavras_sem_nota.py`) → fácil: ornamentos e cromatismos (`niveis.py`) → quantização →
   sílabas (`letra.py`; japonês em moras, `japones.py`) → qualidade do acorde pela voz
   (`harmonia.corrigir_qualidade`) → versões (Acordes; acompanhamento no teor,
   `acompanhamento.py`; Híbridos/IAs) → introdução/final gerados (`introducao.py`) →
   choques voz × acompanhamento (`harmonia.tirar_choques`) → mãos tocáveis e dedos
   (`maos.py`) → `montar_partitura` (armadura por frase `armaduras.py`, marcas, 8va, pedal,
   fermata, cifras depois do makeNotation) → PDF (Verovio + `dedos_ao_lado` +
   `pedal_continuo` + Chrome) → MIDI/prévia (dinâmica vira volume, pedal vira CC64) →
   `cache/sincronia_original.json` (visualizador segue a gravação original).

Registros de cada etapa em `saida/<música>/cache/*.json` (proteção, palavras, harmonia,
mãos, introdução, final, cromáticas do fácil, sincronia).

## 3. Decisões aprovadas pelo usuário (não desfazer sem perguntar)

- Validação de mudança musical = **página às cegas com a partitura visível** (só ouvir
  trecho curto não basta), mesmo piano pra todas as opções, dedos escondidos até revelar,
  versões de notas iguais agrupadas, "onde muda" por par, resultado copiável.
  Geradores: `comparacao_cega.py` (biblioteca real) e as páginas em `trabalho/*_20261110/`.
- Revisão cega dos exemplos confirmou melhora das técnicas (proteção, mãos, harmonia).
- Introdução e final gerados: os 5 teores aprovados nos 3 níveis (nota 5). Épica precisa de
  peso e tensão (oitavas graves, bVI–bVII, dominante sus4, crescendo mp→f→ff); calma/lenta:
  esquerda só com notas longas; emotiva difícil em semínimas com iv menor.
- Dedos **ao lado** da nota (esquerda; direita se a esquerda estiver ocupada; em cima só
  sem lugar). **8va** em trechos agudos. **Pedal em linha** com entalhe "^" na troca.
- Sem CI e sem autenticação nos projetos pessoais (memória do karaokê vale aqui também).

## 4. Pendências (prioridade)

### Sessão Windows 2026-11-10 (noite) — feito

- Dependências novas instaladas; suíte 102 OK. `validar_biblioteca.py` agora acha o áudio das
  músicas sem `cache/transcricao.json` (antes só 1 de 9 regenerava) e tem `--so`.
- Biblioteca inteira regenerada com o pipeline novo (`trabalho/validacao_20261110/`).
  **Revisão cega do usuário (música inteira):** quase empate, o novo ganhou 8×4 onde ele
  escolheu → mudanças mantidas. Recado forte: **o fácil (Acordes) "não parece a música"**;
  ele quer a melodia preservada ao máximo no fácil. Médio Híbrido AMT "muito melhor".
  No Surprises: melodia soa desafinada. Baby: desvio do DTW piorou muito (5,4 → 24,5 s no
  Híbrido difícil) — investigar (fase do compasso?).
- `maos.clarear_grave` (grave embolado: biblioteca toda de 35,7/min → 0 no Acordes médio),
  kana espaçado + grafia (とう/は), cifra em compasso só de pausa, `--grave-embolado` (antigo).
- `--facil-fiel`: fácil com a melodia do médio (grade 1/2, sem cortar passagens/cromatismos,
  sem transpor). `--gravado`: versão **Híbrido Gravado** (`gravado.py`: piano Kong + violão
  Basic Pitch das faixas do htdemucs_6s na esquerda). `comparacao_completa.py`: página às
  cegas com a **música inteira** (o usuário prefere isso a trechos; versão por lado com `pasta|Versao`).
- Exemplo 03 refeito (trecho "machucar meu coração"). `--do-karaoke` testado (Águas de
  Março; corrigido int64 no JSON das mãos). Experimento 6 faixas rodado sem referências
  (concordância 4×6: 60–87% de fundamental). Tensão tonal (pacote `partitura`) no relatório.
- Conjunto de teste do karaokê (o usuário conhece as músicas): `trabalho/karaoke_teste_20261110/`
  (11 músicas, todas as versões + Gravado).

### Esperando o julgamento do usuário (páginas em `trabalho/`)

| página | decide |
|---|---|
| `validacao_grave_20261110/pagina_completa` | `clarear_grave` fica como padrão? |
| `facil_fiel_20261110/pagina_completa(_hibrido)` e `karaoke_facil_fiel_20261110/pagina` | `--facil-fiel` vira o fácil padrão? |
| `acompanhamento_20261110/pagina_completa` | qual teor (ou o de hoje) por música |
| `gravado_20261110/pagina_completa` e `karaoke_teste_20261110/pagina_gravado` | Híbrido Gravado × Híbrido AMT |

### Ainda abertas

1. Cifras de referência conferidas à mão (CSV) pro `experimento_6faixas.py` — só o usuário.
2. Piano grave vaza pra faixa de baixo do htdemucs_6s (JVKE 16%, Videotape 36%): transcrever
   também o baixo no `gravado.py` pode completar a esquerda.
3. Linux: métricas da pesquisa ainda não implementadas (2º dedilhado, ritmo LHL/RGC, MGEval);
   calibrar `maos.PERFIL` com alguém tocando.

## 5. Pegadinhas técnicas

**Windows / ambiente**
- Verovio `loadFile` falha com acento no caminho → `loadData(texto)`. AMT-APC: `python -X utf8`.
- `gerar.py` roda como `__main__`; `import gerar` pega outra cópia (com `SR_GRADE` padrão):
  o passo da grade viaja em `Grade.passo`.
- faster-whisper: passar o áudio já carregado (PyAV novo quebra), `vad_filter=False`, letra
  oficial não vai como `initial_prompt`.
- curl no Windows manda acento em cp1252; testar a API com Python/urllib.
- Pop2Piano precisa do `_stubs/essentia` no `sys.path` antes do `transformers`.
- Etude (piano cover) descartado: 16 GB de VRAM e Linux + conda.

**music21 / Verovio / desenho**
- Cifra inserida antes do `makeNotation` no meio de uma nota cria 2ª voz só de pausas →
  cifras entram depois, direto no compasso (`montar_partitura`).
- `spanner.Ottava(transposing=True)` exporta oitavas erradas → escrever as notas uma oitava
  abaixo com `transposing=False`; `sincronia.py` soma a oitava ao ler `octave-shift`.
- Verovio não desenha `pedal type="change"` (MusicXML) nem `dir="bounce"` (MEI): só o 1º
  colchete aparece → `gerar.pedal_continuo` redesenha a linha no SVG.
- Verovio só põe dedilhado em cima/embaixo → `svgAdditionalAttribute: fing@startid` +
  `gerar.dedos_ao_lado`. O `<text>` do dedo vem com `font-size="0px"`; o tamanho real está
  no `tspan`. Glifos da cabeça: E0A2 inteira, E0A3 mínima, E0A4 semínima (largura SMuFL);
  1 espaço de pauta = 180 unidades no SVG (glifo em scale 0.72).
- Verovio não conta a linha de pedal na colisão: `spacingSystem: 12` (`OPCOES_DEDOS`).
- Visualizador: cache em `cache/visor_*.json` com versão (`web/partitura.py VERSAO`, hoje 11);
  mudou o desenho, suba a versão.
- Modo foco (celular): `/api/partitura?layout=retrato|paisagem` desenha página estreita e
  contínua (`web/partitura.LAYOUTS`), cache em `visor_<nome>.<layout>.json`. Tela >= 1000 px
  usa a página A4.

**Integração com o karaokê**
- `alinhamento.py` importa `karaoke/server` (sys.path no fim). `utils.audio` importa pydub,
  que no Python 3.13 pede `audioop-lts` → substituto que carrega com librosa.
- O karaokê apaga o `original.mp3` depois de separar: `--do-karaoke` soma voz + acompanhamento.
- O Demucs nomeia a pasta pelo arquivo: copiar o `backing_track.mp3` com o slug no nome.
- O alinhamento usa a GPU fora do lock do servidor do karaokê: não rodar durante partida.

**Páginas locais / navegador**
- Páginas abertas por `file://` guardam imagens em cache: usar `?v=<Date.now()>` nos src.
- A extensão do Chrome não abre `file://`: servir com `python -m http.server` pra conferir.
- `pkill -f "<padrão>"` dentro de um comando que contém o padrão mata o próprio shell:
  matar pelo PID da porta (`ss -ltnp`).

## 6. Mapa dos arquivos novos (2026-11-10)

| arquivo | papel |
|---|---|
| `maos.py` | modelo da mão (Parncutt/Jacobs), dedilhado por DP, correção de trechos intocáveis |
| `alinhamento.py` | letra oficial pelo MMS_FA do karaokê; `musica_do_karaoke` |
| `palavras_sem_nota.py` | nota pra palavra cujo ataque o detector não pegou |
| `armaduras.py` | armadura por frase, mínimo 16 compassos |
| `harmonia.py` | qualidade do acorde pela voz; tira voz em semitom com a voz |
| `introducao.py` | introdução e final gerados por teor e nível |
| `acompanhamento.py` | esquerda da música inteira no teor |
| `japones.py` | letra em moras (romaji/kana) |
| `metricas.py` | métricas de validação (fidelidade, melodia, dificuldade, grave, groove, tensão) |
| `comparacao_cega.py` | página cega antes × depois com trechos reais |
| `validar_biblioteca.py` | validação da biblioteca num comando |
| `experimento_6faixas.py` | experimento htdemucs × htdemucs_6s |
| `avaliar_maos.py` | trechos difíceis pra mão em partituras prontas |
