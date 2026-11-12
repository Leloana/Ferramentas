# Handoff — Partitura (estado em 2026-11-11)

Música com voz → partitura de piano com a letra embaixo das notas (PDF, MusicXML, MIDI,
prévia em áudio), três níveis, interface web. **Sempre algoritmo**: modelos de áudio
(Demucs, torchcrepe, Whisper, MMS_FA do karaokê, Pop2Piano, AMT-APC) + regras musicais.
**Nada de LLM na geração nem na validação** (pedido do usuário).

Leia nesta ordem: este arquivo → `README.md` (uso e opções) → `PROXIMA_ETAPA.md` (plano por
frentes) → `METRICAS_VALIDACAO.md` (como medir) → `HISTORICO.md` (crônica detalhada, §1–42).

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
- Suíte: `python -m unittest test_*` (181 testes em 2026-11-12, todos OK no Linux).
- O AMT-APC no venv também pede `tqdm` (está no `modelos/amt-apc/requirements.txt`).
- madmom no venv (GitHub, ver requirements.txt) pras batidas do modo leve.
- AMT-APC instalado aqui também (`modelos/amt-apc`, torch CPU no venv): o modo leve roda no
  Linux (~8 min por música do zero neste notebook, ~30 s do cache). Áudio de teste:
  `entrada/aguas_de_marco_BnB1G63XvCQ.wav` (vídeo de origem do karaokê).

## 2. Pipeline (ordem real em `gerar.py`)

**Padrão desde 2026-11-11: modo leve** (`--leve`, `gerar_nivel_leve`), o que o site usa. **Sai sem
letra** (letra precisa de Demucs + tempos das palavras, caro; decisão do usuário). Ordem:

1. Batidas e tempo 1 pelo **madmom** (`batidas_madmom`; sem ele, librosa + `fase_pelo_midi` +
   `corrigir_fase`) → `Grade`; acordes da mistura (croma + Viterbi).
2. AMT-APC (`amtapc.py`, estilo do médio, uma vez por música, cache `cache/amtapc_medio.mid`).
3. Médio: `reduzir_mao` → `corrigir_tom` (`tonalidade.py`) → **repetições escritas iguais**
   (`repeticoes.padronizar`: lags pelo áudio, confirmação pelas notas, versão real mais votada).
4. Fácil/difícil derivados do médio (`derivados.py`).
5. **Tocabilidade por regra** (`tocavel.ajustar`): fácil com oitava por frase (se a leitura melhora)
   e síncope no tempo; grave da direita pra esquerda; médio com síncope da esquerda no tempo e
   oitava da esquerda por DP. Depois `juntar_repetidas_esquerda` e `maos.tornar_tocavel` (dedos).
6. `montar_partitura`: armadura pelo tom (`armaduras.py`), grafia pela cifra sem dobrado e
   cromatismo pela direção, sem cifra desenhada, **8va por DP** de linhas suplementares (altura
   que soa no MusicXML) → PDF (Verovio + `dedos_ao_lado` sem sobreposição) → prévias.

O pipeline completo abaixo continua valendo pra linha de comando, `--do-karaoke` e as versões
Acordes/Híbridos (com letra).

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

### Feito em 2026-11-12 (Linux, HISTORICO §44)

- **3/4 de verdade** no modo leve (`metrica.py`): o compasso de 3 tempos do madmom sai em 3/4. 4/4 idêntico
  ao de antes nas 5 músicas de teste. Na Windows, depois do madmom instalado e da biblioteca regenerada sem
  cache, Piano Man deve sair em 3/4: conferir a partitura. 6/8 segue sem escrita própria.
- **AMT-APC carregado no site** (`amtapc.py --servico`, sobe com o `run.py`): falta medir o ganho na Windows
  (esperado ~8 s por música). `PARTITURA_SEM_SERVICO=1` desliga.
- `comparacao_cega`/`comparacao_completa` com AMT-APC nos três níveis por padrão.
- Os itens 1 a 4 abaixo continuam: dependem da Windows ou de decisão do usuário.

### Retomar daqui (2026-11-12) — pendências pra amanhã

**Estado:** tudo commitado e enviado (último: `25f3be4`); suíte 173 OK. O app **não está rodando**
(caiu com o fim da sessão): `cd partitura; .\venv\Scripts\python.exe run.py --lan` → celular em
http://192.168.15.6:8030 (o venv usa o Python 3.12 da Store, já liberado no firewall).

**Decidir / fazer (usuário):**
1. **Instalar o madmom** na Windows (a instalação do GitHub foi bloqueada pela permissão automática):
   `.\venv\Scripts\python.exe -m pip install cython; .\venv\Scripts\python.exe -m pip install --no-build-isolation git+https://github.com/CPJKU/madmom.git`.
   Sem ele: andamento às vezes dobrado (Someone Like You 136 em vez de 68) e valsa em 4/4 (Piano Man).
   Depois de instalar, regenerar a biblioteca **sem** `--reusar-cache` (as batidas do cache são do librosa).
2. **Página às cegas** (antes × depois do teste em massa, 3 músicas × 3 níveis):
   `trabalho/escuta_20261111/escuta/index.html` (servir com `python -m http.server 8040` dentro de
   `trabalho/escuta_20261111` pra ouvir no celular). O usuário ouviu e achou "bem mais harmônica a nova
   partitura"; falta colar as notas. Se reprovar algo, voltam ao antigo: `gerar.GRAFIA_ESCALA`,
   `--acordes mistura`, `derivados.DIFICIL["evitar_choque"]`, `derivados.FACIL_BAIXO = (36, 55)`.
3. **Propostas fora do padrão:** `niveis.GRAVE_MINIMO = 36` (baixo do médio/difícil sem descer de Dó2:
   −30% de linhas suplementares na clave de fá, muda o peso do baixo) e `--dinamica` no site (p/mp/mf/f
   pela intensidade, calibrado: ~5 marcas por música).
4. **Limpeza opcional:** `trabalho/escuta_20261111` (156 MB, depois de ouvir); as cópias antigas sem áudio
   "Cálice" e "No Surprises" em `saida/` (as versões com áudio ficam); `trabalho/lixeira/` tem 2 músicas
   apagadas pelo usuário no site (esvaziar só se ele pedir). `trabalho/lote/` (~12 GB) fica: dados de calibração.

**Feito nesta sessão (2026-11-11, tarde/noite, Windows):**
- Teste em massa de 537 músicas integrais e padrões novos do modo leve (HISTORICO §43, `trabalho/lote/LEIAME.md`).
- Site: Gerar volta pra biblioteca com o card carregando; toque no card = tela de espera em tela cheia
  (etapas, tempo, tentar de novo/remover); progresso real e suave (download em bytes pelo yt-dlp,
  segmentos do AMT-APC, demais etapas pelo tempo esperado; nunca desce; antes pulava de 8% pra 90%
  porque a saída do gerar.py chegava toda no fim); renomear (lápis no card e menu ⋯) e apagar (vai pra
  `trabalho/lixeira`); bolinha da posição seguindo o áudio depois do 1º toque; cursor das notas não corre
  mais até o fim da linha e volta na nota longa (limites pela barra de compasso); `PARTITURA_SAIDA` e
  `run.py --porta=N` pra servir outra biblioteca.
- Andamento: era preso a valores fixos (129, 123, 117...) pela mediana em quadros do detector; agora a
  média dos intervalos (`gerar.periodo_das_batidas`). Biblioteca (29 músicas) regenerada com isso.
- Velocidade medida: geração limpa no site ~37 s pra 4 min (AMT-APC 9 s carregando o modelo a cada
  música, prévias 6 s, PDFs 3,5 s). Ideia não feita: manter o AMT-APC carregado no servidor (~−8 s).
- Pendências antigas que seguem abertas: 6/8 (3/4 feito em 2026-11-12), letra no fluxo padrão.

### Retomar daqui (2026-11-11, noite, Windows — teste em massa, HISTORICO §43)

- `lote.py` + `qualidade.py`: 537 músicas integrais em `trabalho/lote/` (mapa em `trabalho/lote/LEIAME.md`:
  áudio, cache do fluxo, MusicXML no padrão atual, `medidas/`, `relatorio.md`; referência
  `medidas/referencia_20261111.json`). Biblioteca do site (`saida/`) regenerada no padrão novo. Adotados: grafia pela escala, `--acordes ambos`, difícil sem
  choque, baixo do fácil Fá2–Mi3 (validado em 473 músicas fora da calibração).
- **Ouvir a página às cegas** `trabalho/escuta_20261111/escuta/index.html` (antes × depois). Se
  reprovar algo: `gerar.GRAFIA_ESCALA`, `--acordes mistura`, `derivados.DIFICIL["evitar_choque"]`,
  `derivados.FACIL_BAIXO = (36, 55)` voltam ao antigo.
- Decidir: `niveis.GRAVE_MINIMO = 36` (baixo mais legível no médio/difícil) e `--dinamica` no site.
- **Instalar o madmom na Windows** (README, "Montar num servidor"): o site daqui roda com a grade do
  librosa (andamento dobrado em parte das músicas, compasso sempre 4/4).

### Retomar daqui (fim da sessão 2026-11-11)

- Tudo commitado e enviado (`73f0d4d`, `01fed37`, `50f0720` + docs). Suíte 161 OK.
- Músicas de teste no Linux (`entrada/`, `saida/`, fora do git): Águas de Março, Ode, Fuyu no
  Hanashi, Anna Júlia, Cálice, com o MIDI do AMT-APC em cache (regerar do cache leva ~30 s cada).
- Antes de qualquer mudança: `python regressao.py saida --musicas "Ode,Aguas de Marco,Fuyu no
  Hanashi,Anna Julia,Calice" --base trabalho/regressao_base_20261111.json`.
- Próximo passo combinado: item 2 ou 3/4 de verdade da lista "Próximos" abaixo (o usuário escolhe).
- Windows: instalar madmom do GitHub (README, "Montar num servidor") e regenerar a biblioteca do
  cache (`--reusar-cache`): o MusicXML antigo tem a 8va errada e a grade antiga.

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

### Regressão automática (usar a cada mudança)

`python regressao.py saida --musicas "Ode,Aguas de Marco,Fuyu no Hanashi,Anna Julia,Calice" --base
trabalho/regressao_base_20261111.json` (as 5 músicas de teste do Linux, modo leve). Sai com 1 e
lista o que piorou. Depois de uma melhoria aceita, `--salvar` a nova referência.

### Próximos (pesquisa 2026-11-11, HISTORICO §41)

1. ~~Batidas e tempo 1 pelo madmom~~ feito (§42; Fuyu era grade com batidas a mais, não 2/4).
   3/4 feito (2026-11-12, `metrica.py`). Falta: 6/8 e fase por trecho
   (Shibata et al. 2021) se aparecer música com troca de métrica.
2. Grafia ps13 (`partitura.musicanalysis.estimate_spelling`), armadura e raiz do acorde de desempate.
3. Seções por spectral clustering (McFee e Ellis 2014) → ritornelo e casa 1/2.
4. Métricas do Score Analyzer (Sébastien et al. 2012) e MV2H entre níveis na `regressao.py`.
5. Dedilhado por HMM (Nakamura et al. 2020) e redução com dificuldade controlada (Nakamura e Yoshii 2018).

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
4b. Repetições escritas iguais (`repeticoes.py`, HISTORICO §40–41): ouvindo "ficou igual"; o
   usuário só vai saber tocando. Padrão = versão real mais votada menos leitura. Falta: repetição deslocada meio compasso (Fuyu, lag 38,5
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
| `regressao.py` | mede legibilidade/tocabilidade das partituras prontas e acusa piora contra uma referência |
| `repeticoes.py` | repetições pelo áudio + notas, escritas iguais por consenso (2026-11-11) |
| `tocavel.py` | tocabilidade por regra no modo leve: medir (síncopes, saltos, densidade, posição) e corrigir (2026-11-11) |
| `tonalidade.py` | tom por trecho (Krumhansl + Viterbi) e nota fora do tom do arranjo da IA (2026-11-11) |
| `lote.py` | teste em massa do modo leve: baixar, AMT-APC em lote na GPU, gerar em paralelo, medir, comparar, `--ajustes` |
| `qualidade.py` | métricas de leitura, tocabilidade e som (croma × gravação com pedal, choques, acidentes evitáveis) |
| `dinamica.py` | p/mp/mf/f pela intensidade da gravação (`--dinamica`, opcional) |
| `metrica.py` | tempos por compasso da música (3/4 ou 4/4, do madmom) lidos pelos passos do modo leve (2026-11-12) |
