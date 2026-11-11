# Handoff — Partitura (estado em 2026-11-11)

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
- Suíte: `python -m unittest test_*` (158 testes em 2026-11-11, todos OK no Linux).
- AMT-APC instalado aqui também (`modelos/amt-apc`, torch CPU no venv): o modo leve roda no
  Linux (~8 min por música do zero neste notebook, ~30 s do cache). Áudio de teste:
  `entrada/aguas_de_marco_BnB1G63XvCQ.wav` (vídeo de origem do karaokê).

## 2. Pipeline (ordem real em `gerar.py`)

**Padrão desde 2026-11-11:** o site gera só a versão **AMT-APC** nos 3 níveis com `--leve`
(`gerar_nivel_leve`): sem Demucs/CREPE/Whisper, batidas e acordes da mistura, tempo 1 pelas
notas graves do AMT-APC, `corrigir_tom` (`tonalidade.py`), fácil e difícil derivados do médio
(`derivados.py`), mãos tocáveis, partitura. **Sai sem letra.** O pipeline completo abaixo
continua valendo pra linha de comando, `--do-karaoke` e as versões Acordes/Híbridos.

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
- **8va por programação dinâmica** (2026-11-11): só entra quando reduz linha suplementar; em cima e
  embaixo pesam igual ("escrever lá embaixo é tão ruim quanto lá em cima") e nota embaixo da pauta
  dentro da 8va é proibida. `gerar.OITAVA_ABRIR` 6, `OITAVA_PESO_EMBAIXO` 100.
- Dedos **ao lado** da nota (esquerda; direita se a esquerda estiver ocupada; em cima só
  sem lugar). **8va** em trechos agudos. **Pedal em linha** com entalhe "^" na troca.
- Sem CI e sem autenticação nos projetos pessoais (memória do karaokê vale aqui também).
- **AMT-APC é a base de tudo** (usuário, 2026-11-11). Escuta 2026-11-11: é a melhor versão, até que o Híbrido. Site, biblioteca e aba
  Karaokê usam AMT-APC nos três níveis; `--versoes` escreve só o pedido.
- **Médio é a base** (`--derivar` padrão): fácil = melodia do médio + uma nota grave por acorde;
  difícil = 3ª/6ª embaixo das longas, oitava nos picos, arpejos, pedal por acorde, fermata.
  Acréscimos só com a tríade (a 7ª detectada erra mais). `--sem-derivar` volta ao antigo.
- **Sem cifra em cima da pauta** (usuário, 2026-11-11: "atrapalha"). `gerar.MOSTRAR_CIFRAS`
  falso por padrão; o acorde detectado continua decidindo a grafia; `--cifras` volta a desenhar.
- Melodia reconhecível: nota repetida colada sem sílaba vira sustentada; nada acima da nota
  cantada; bordadura falsa A-B-A some; prévia com a melodia em destaque (`gerar.DESTAQUE`).
- Melodia no tom: afinação da gravação descontada e nota duvidosa puxada pra escala
  (`afinacao.py`, `--melodia-crua` desliga).

## 4. Pendências (prioridade)

### Direção (usuário, 2026-11-11)

**Usar o máximo de ferramentas determinísticas pra deixar tudo mais tocável.** O modelo de IA
(AMT-APC) dá o arranjo; daí pra frente, regras, DP e métricas fechadas (mesma entrada, mesma
saída) corrigem o que não cabe na mão e o que atrapalha a leitura (armadura, grafia). Toda mudança passa por métrica no relatório + página às
cegas com a música inteira.

### Sessão 2026-11-10 (noite) e 2026-11-11 (madrugada) — feito

- Melodia: afinação descontada + nota duvidosa puxada pra escala (`afinacao.py`; Don't Look Back
  in Anger 179/590 fora do tom → 0–4% na biblioteca); repetida colada sem sílaba vira sustentada;
  `limpeza.py` (melodia no topo, bordadura falsa, repetidas da esquerda); prévia com destaque.
- `--derivar` padrão (`derivados.py`); `tonalidade.py` corrige nota fora do tom do AMT-APC
  (348 notas na biblioteca, músicas limpas intocadas); `corrigir_fase` (tempo 1 meio compasso
  deslocado em ~metade das músicas).
- `--leve` e `--versoes`: Rosa de Hiroshima do zero em CPU 87 s; do cache 2 min → 11 s.
- Front refeito (buscar, gerar num toque, tocar e ler, celular primeiro); README com montagem
  num servidor.
- Armadura pelo tom (Krumhansl) e grafia da cifra sem dobrado: Águas de Março saiu de Mi♭ com
  dobrados bemóis pra Si♭, acidentes −15%. Detalhes no HISTORICO §31–35.

### Rodada 3 (2026-11-11, tarde) — direção do usuário

**Modo leve é o padrão; letra fica fora dele** (precisa do Demucs + tempos das palavras, caro).
Objetivo: leve rápido, legível, fácil e fiel à música. Feito: dedo não entra na cabeça vizinha
(segunda no acorde); fácil com oitava por frase (só se o custo de leitura final cair); nota grave
da direita pra esquerda quando a esquerda alcança. Página às cegas do fácil (Fuyu, Águas, Anna
Júlia): aprovada ("ficou muito boa a simplificação"). Dedos: nenhum sobreposto nas 15 partituras. Atraso das batidas:
medido e descartado (HISTORICO §38).

### Abertas

1. **Letra no fluxo padrão.** O AMT-APC (leve ou completo) sai sem letra, então o site perdeu a
   letra embaixo das notas. Caminhos: (a) sílabas na voz de cima da direita do AMT-APC (precisa
   Whisper/MMS_FA, sai do "sem GPU"); (b) HibridoAMT como opção "com letra". Decisão do usuário.
2. **Tocabilidade e leitura do AMT-APC, determinísticas.** Feito em 2026-11-11 (`tocavel.py`,
   só no modo leve, `--sem-ajuste` desliga): síncope que atravessa o tempo vai pro tempo (fácil nas
   duas mãos, médio só na esquerda), oitava da esquerda por DP (fácil e médio), grafia cromática
   pela direção. Águas de Março: fácil síncopes da direita 94 → 0; médio síncopes da esquerda
   105 → 7 e mudanças de posição 9,2 → 5,7/min. Página 1 (Águas, Ode): usuário aprovou ("ficou
   muito bom"). Depois entrou a trava do salto (síncope não muda se a mão não chega na próxima nota
   a tempo, `maos.PERFIL`): o fácil de Fuyu tinha ganho 2 trechos difíceis. Página 2
   (Fuyu no Hanashi, Anna Júlia, Cálice): aprovada, "as músicas são iguais, mas a partitura ficou
   bem mais legível". Fica como padrão do modo leve. Difícil: a direita muda de posição 35–50/min (médio 15–19); quem dobra é a 3ª/6ª embaixo
   das notas longas (sem ela 24–35/min); restringir a nota sozinha/abertura ou conduzir a voz
   interna não muda nada (medido, `trabalho/tocavel_20261111/exp_dificil.py`): é o próprio
   tocar em terças. Fica como está, é o que faz o difícil ser difícil. Falta: rodar a armadura
   e o `tocavel` na biblioteca toda; levar o `tocavel` pro pipeline completo (respeitando a melodia
   protegida). Teto de densidade: não precisou, a grade e a derivação já seguram (medido).
3. Baby: desvio do DTW 5,4 → 24,5 s no Híbrido difícil. Ver se o `corrigir_fase` resolveu
   (`validar_biblioteca.py --so baby` na Windows). No Surprises desafinada: conferir com o `afinacao.py`.
4. Front novo não usa `/api/karaoke`, `/api/gerar_karaoke`, `/api/variacao` nem `DELETE /api/jobs`
   (aba Karaokê e "Outra variação" saíram da tela); `/api/gerar` aceita `introducao/final/estilo`
   que o leve ignora. Decidir: volta na tela ou sai do servidor.
4b. Repetições escritas iguais (`repeticoes.py`, HISTORICO §40): **esperando a página às cegas**
   `trabalho/rodada4_20261111/pagina`. Falta: repetição deslocada meio compasso (Fuyu, lag 38,5
   compassos) pede corrigir a métrica (compasso de 2 tempos) usando a própria repetição; sinal de
   repetição/ritornelo pra encurtar a partitura.
5. Cifras de referência conferidas à mão (CSV) pro `experimento_6faixas.py` — só o usuário.
6. Piano grave vaza pra faixa de baixo do htdemucs_6s (JVKE 16%, Videotape 36%): transcrever
   também o baixo no `gravado.py`.
7. Métricas da pesquisa não implementadas (2º dedilhado, ritmo LHL/RGC, MGEval); calibrar
   `maos.PERFIL` com alguém tocando.

### Superadas pela escolha do AMT-APC com níveis derivados

As páginas de 2026-11-10 (`validacao_grave`, `facil_fiel`, `acompanhamento`, `gravado`,
`karaoke_teste`) ficam como registro; `clarear_grave` segue padrão. `--facil-fiel`, `--gravado`
e `--acompanhamento` continuam na linha de comando, fora do site.

## 5. Pegadinhas técnicas

**Windows / ambiente**
- torchaudio >= 2.9 lê áudio pelo torchcodec; o lançador do `amtapc.py` cai pro soundfile.
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
- **8va (corrigido 2026-11-11):** no MusicXML a altura é a que **soa**; o Verovio desenha uma
  oitava abaixo sob o `octave-shift` (MEI: `oct` escrito, `oct.ges` sonoro). O código antigo baixava
  a nota E o Verovio baixava de novo: saía desenhada duas oitavas abaixo (o "manda 8va e põe as
  notas lá embaixo" do usuário). Agora `_oitava_acima` não mexe na altura e o `sincronia.py` não
  soma oitava. MusicXML gerado antes disso fica com a 8va errada no visualizador: regenerar
  (`--reusar-cache`) a biblioteca da Windows.
- Verovio não desenha `pedal type="change"` (MusicXML) nem `dir="bounce"` (MEI): só o 1º
  colchete aparece → `gerar.pedal_continuo` redesenha a linha no SVG.
- Verovio só põe dedilhado em cima/embaixo → `svgAdditionalAttribute: fing@startid` +
  `gerar.dedos_ao_lado`. O `<text>` do dedo vem com `font-size="0px"`; o tamanho real está
  no `tspan`. Glifos da cabeça: E0A2 inteira, E0A3 mínima, E0A4 semínima (largura SMuFL);
  1 espaço de pauta = 180 unidades no SVG (glifo em scale 0.72).
- Verovio não conta a linha de pedal na colisão: `spacingSystem: 12` (`OPCOES_DEDOS`).
- Visualizador: cache em `cache/visor_*.json` com versão (`web/partitura.py VERSAO`, hoje 14);
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
- Laço `while read ... done <<EOF` com `python`/`yt-dlp` dentro: eles leem o stdin e engolem as
  linhas seguintes; usar `</dev/null` em cada comando do laço.
- `pkill -f "<padrão>"` dentro de um comando que contém o padrão mata o próprio shell:
  matar pelo PID da porta (`ss -ltnp`).

## 6. Mapa dos arquivos novos (2026-11-10 e 11)

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
| `gravado.py` | Híbrido Gravado: piano (Kong) + violão (Basic Pitch) das 6 faixas na esquerda |
| `comparacao_completa.py` | página às cegas com a música inteira (`pasta\|Versao - Nivel` por lado) |
| `afinacao.py` | afinação da voz descontada e nota duvidosa puxada pra escala (2026-11-11) |
| `limpeza.py` | melodia no topo, bordadura falsa, repetidas da esquerda (2026-11-11) |
| `derivados.py` | fácil e difícil derivados do médio (2026-11-11) |
| `repeticoes.py` | repetições pelo áudio + notas, escritas iguais por consenso (2026-11-11) |
| `tocavel.py` | tocabilidade por regra no modo leve: medir (síncopes, saltos, densidade, posição) e corrigir (2026-11-11) |
| `tonalidade.py` | tom por trecho (Krumhansl + Viterbi) e nota fora do tom do arranjo da IA (2026-11-11) |
