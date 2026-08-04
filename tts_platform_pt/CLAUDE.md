# CLAUDE.md

Orientações para o Claude Code ao trabalhar neste subprojeto.

## Visão Geral

Servidor FastAPI local que sintetiza fala em português com **XTTS-v2**
(`coqui/XTTS-v2`, Hugging Face — multilíngue, clonagem de voz zero-shot),
com normalização opcional de texto via **Ollama** local antes da síntese.
Frontend em Vanilla JS (sem build step), no mesmo padrão do `karaoke/`.

Idioma do projeto: **português**. Logs, comentários e mensagens de UI em
PT-BR; nomes de função/classe/variável em inglês — mesmo padrão dos demais
subprojetos do repositório.

## Como Rodar

```powershell
cd tts_platform_pt
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn server.main:app --reload --port 8011
```

Pré-requisitos externos: Ollama aberto com `qwen3:0.6b` baixado (opcional — o
checkbox "Normalizar" no front é o toggle real; desmarcado, o Ollama nunca é
chamado. Marcado sem Ollama disponível, cai em fallback e usa o texto
original); GPU CUDA recomendada (fallback automático para CPU, mais lento).

## Arquitetura

- `server/main.py` — entrypoint FastAPI; insere `server/` no `sys.path` (igual
  ao `karaoke/server/main.py`) para permitir imports diretos por nome de
  módulo (`import config`, `from routes.synthesize import router`).
- `server/config.py` — constantes: paths (`VOICES_DIR`, `OUTPUT_DIR`), porta,
  nome do modelo XTTS-v2, modelo Ollama default.
- `server/state.py` — singleton `get_tts_engine()`, evita recarregar o modelo
  a cada request.
- `server/engine/tts_engine.py` — wrapper do XTTS-v2 (`TTS.api.TTS`). Aceita a
  licença CPML programaticamente (`COQUI_TOS_AGREED=1`). Fallback CUDA → CPU
  automático no carregamento, igual ao `stt_engine.py` do karaoke.
  `synthesize(..., speed=1.0)` expõe o `speed` nativo do XTTS-v2 (ajusta o
  `length_scale` na própria geração, sem stretch de pós-processamento nem
  mudança de pitch) — faixa segura ~0.7-1.3, fora disso a voz degrada
  (artefatos, cadência robótica). `scripts/gerar_video.py` usa 1.20 como
  padrão (ver abaixo); `POST /api/synthesize` aceita `speed` no corpo.
- `server/engine/text_preprocessor.py` — `normalize(texto)` via
  `ollama.generate(..., format="json")`, no mesmo estilo de
  `youtube_music_playlist_organizer/core/classifier.py`. Retorna
  `(texto, aviso)`: `aviso` é `None` em caso de sucesso, ou uma string
  explicando por que a normalização foi pulada/falhou (VRAM insuficiente,
  Ollama fora do ar, JSON inválido) — a síntese nunca deve quebrar por causa
  desse pré-processamento opcional, e o front mostra o aviso quando existe.
  `num_ctx` do Ollama é escolhido dinamicamente por chamada
  (`_pick_num_ctx()`), reservando VRAM pro XTTS-v2; se não sobrar nem o
  mínimo, pula o Ollama de vez (ver Gotchas).
- `server/routes/synthesize.py` — `POST /api/synthesize`.
- `server/routes/voices.py` — `GET/POST /api/voices` (listar/enviar amostra
  de clonagem).
- `server/voices/custom/` — `.wav` de referência enviados pelo usuário
  (gitignored).
- `server/output/` — `.wav` gerados, servidos via `StaticFiles` em `/audio`
  (gitignored).
- `scripts/gerar_video.py` — automatiza a produção de áudio a partir de um
  roteiro: sintetiza o texto exatamente como está no arquivo, sem cortar em
  blocos (isso já é responsabilidade de quem escreve o `texto.md` de cada
  parte, ver convenção de pastas abaixo). Voz padrão é a masculina (Dionisio
  Schuyler) — a feminina só é gerada se pedida explicitamente com `--voz`.
  Cliente HTTP do próprio `/api/synthesize` — requer o servidor rodando. Ver
  `Projetos/Video_N/<nome>/` para convenção de pastas de entrada/saída.
- `scripts/gerar_imagens.py` — gera as imagens de fundo (uma por FRASE, não
  por parte inteira) via ComfyUI local, a partir do manifesto que
  `gerar_video.py` já produziu. Cliente HTTP da API do ComfyUI
  (`127.0.0.1:8188`), não da plataforma de TTS.
- `comfy/image_krea2_turbo_t2i.json` — workflow do ComfyUI (formato API,
  exportado via Workflow → Export (API)) usado por `gerar_imagens.py`.
  Modelo: `krea2_turbo_fp8_scaled` (UNET) + `qwen3vl_4b_fp8_scaled` (CLIP,
  também usado como LLM de refino de prompt) + `qwen_image_vae`. Reexportar
  aqui sempre que o workflow for alterado na UI do ComfyUI, senão o script
  roda contra uma versão desatualizada do grafo.
- **[comfy/GOTCHAS.md](comfy/GOTCHAS.md)** — leia antes de mexer em
  `gerar_imagens.py`, `montar_video.py` ou no workflow acima. Reúne os
  achados de depuração real da geração de imagem (nudez, texto borrado
  desenhado na cena, formato vertical menos confiável, zoom tremendo,
  prompt bilíngue engasgando o refino, modelo desviando pra conteúdo fora
  do tema/impróprio sem gatilho óbvio no prompt) — cada um custou uma ou
  mais rodadas de geração pra isolar, não repita o trabalho.
- `scripts/montar_video.py` — monta o `.mp4` final de um projeto/parte
  (uma imagem por frase, cada uma com zoom próprio, + áudio + legenda
  queimada) via `ffmpeg`, lido do CLI, não de nenhuma API HTTP. Único dos
  scripts de automação que não depende do
  servidor da plataforma nem do ComfyUI estarem rodando — só precisa que
  `gerar_video.py` e `gerar_imagens.py` já tenham gerado os arquivos daquele
  projeto.
- `scripts/gerar_capa.py` — **passo final obrigatório de todo vídeo**: gera a
  imagem de capa/thumbnail e desenha o título por cima com Pillow — texto
  real, desenhado aqui, não pedido ao modelo de difusão (mesmo motivo do
  `_REGRA_SEM_TEXTO` em `gerar_imagens.py`: o Krea2 não sabe renderizar
  texto legível). **A capa não reaproveita nenhuma imagem do corpo do
  vídeo** — o fundo é uma cena nova gerada no ComfyUI a partir de um
  `--prompt` escrito à mão (reusa `gerar_imagem()` de `gerar_imagens.py`),
  pensada pra ser chamativa o bastante pra fazer alguém parar de rolar o
  feed e clicar, não pra ilustrar uma frase específica da narração (esse é
  o papel das imagens de `imagens/`). `--imagem` pula a geração e usa um
  fundo já pronto (ex.: pra só reajustar o texto do título). Sem
  `--titulo`, usa a 1ª linha de `descricao.md` (sem o "👇" final). Saída em
  `<projeto>/capa.png` (com título) + `<projeto>/capa_fundo.png` (cena sem
  texto, reaproveitável) + `<projeto>/capa_manifesto.json`
  (`prompt_final`/`arquivo_comfy`, mesma lógica de rastreabilidade do
  `_imagens_manifesto.json` — ver convenção de pastas abaixo). Só depende
  do ComfyUI estar rodando quando `--prompt` é usado (i.e., quando não há
  `--imagem`).

## Convenção de pastas: `Projetos/Video_N/<nome-do-projeto>/`

Cada **produção** (uma ideia de vídeo, tenha ela 1 parte ou vire série de
várias) vive dentro de uma pasta numerada `Projetos/Video_N/` — `Video_1` foi
a primeira produção feita (`historia_humanidade`, 5 partes), `Video_2` é a
próxima, e por aí vai. O número é sequencial por **produção**, não por parte:
uma série de 5 partes consome um `Video_N` só, com as 5 pastas de parte
dentro dele. Dentro de cada `Video_N/`, cada parte vive na sua própria pasta,
plana por padrão — `audio/` e `samples_vozes/` só existem enquanto os `.wav`
intermediários ainda são úteis (ver gotcha abaixo) e somem depois.
**Atenção**: `audio/` é nome fixo no código de `gerar_video.py`
(`projeto / "audio"`, e `manifesto["arquivo"]` sempre começa com
`"audio/"`) e `video/` é nome fixo no código de `montar_video.py`
(`projeto / "video" / ...`) — não são preferência de organização, se
restaurar um `.wav` pra retomar edição o nome da subpasta tem que ser
exatamente esse. Os scripts (`gerar_video.py`, `gerar_imagens.py`,
`montar_video.py`, `gerar_capa.py`) resolvem tudo a partir de
`args.manifesto.parent` — não têm ideia de que existe um `Video_N/` por
cima, então mover uma pasta de parte pra dentro/fora de um `Video_N/` nunca
quebra nada neles. Padrão adotado a partir do projeto `historia_humanidade/`:

```
Projetos/Video_N/<nome-do-projeto>/
  texto.md                          # roteiro fonte (só o texto puro da narração)
  vozes.md                          # registro manual: "Mulher: <voz>" / "Homem: <voz>"
  descricao.md                      # legenda + hashtags pra postar (ver abaixo)
  texto_prompts.json                # prompts de imagem reescritos à mão, ver gerar_imagens.py
  <nome>_manifesto.json             # 1 por voz testada (gerar_video.py) — sem sufixo = voz padrão (masculina)
  <nome>_feminino_manifesto.json    # sufixo de voz no nome quando houver mais de uma
  <nome>_imagens_manifesto.json     # 1 só — imagens não dependem de voz, ver abaixo
  imagens/<nome>_FF.png             # imagens de fundo (FF = frase), compartilhadas entre as vozes
  capa_fundo.png                    # cena chamativa gerada pro thumbnail, distinta de imagens/ — ver gerar_capa.py
  capa_manifesto.json               # prompt_final/arquivo_comfy da capa_fundo.png, mesma lógica do manifesto de imagens
  capa.png                          # capa_fundo.png + título desenhado — não depende de voz
  audio/<nome>.wav                  # áudio intermediário (gerar_video.py), descartável depois do vídeo final
  video/<nome>_9x16.mp4             # vídeo final, um por voz
```

- **`descricao.md`**: legenda + hashtags prontas pra copiar e colar direto
  na hora de postar (Reels/Shorts/TikTok) — texto puro, sem cabeçalho
  markdown (nada de `# Legenda`/`# Hashtags`, é pra colar como está).
  Escrito à mão a partir do `texto.md` daquela parte, não é gerado por
  nenhum script: **indicador de parte primeiro** (tipo "Parte 2/5", é a
  primeira linha do arquivo — quem abre o vídeo precisa saber de cara em
  que ponto da série está; na última parte da série vira "Parte N/N
  (final)"), depois gancho de 1-2 frases terminando num emoji temático,
  linha em branco, e um segundo parágrafo de resumo do que a parte cobre.
  Termina com as hashtags. **Hashtags = mesmo bloco-base em toda a série +
  3-5 específicas da parte**: `#historia #humanidade #curiosidades
  #documentario #fatoshistoricos #linhadotempo #conhecimento #shorts
  #reels` sempre presentes (são o "franchise" da série, é o que faz
  alguém que curtiu a parte 1 achar a parte 2), mais umas 3-5 hashtags só
  daquele assunto (ex.: `#escrita #roma #maias` na parte sobre
  civilizações antigas) — não trocar/remover as fixas de uma parte pra
  outra, senão a série para de ficar linkada nas buscas por hashtag.
  Criar junto com o `texto.md` de cada parte, mesmo antes de gerar
  áudio/vídeo — só depende do texto da narração, não
  do resultado final.

- **`texto_prompts.json`**: `{"<frase>": "descrição visual em inglês"}`,
  escrito à mão (por quem estiver rodando o pipeline, não gerado por script)
  pra alimentar `gerar_imagens.py --prompts`. **Por quê não usar o texto
  literal da narração como prompt de imagem**: frases de narração costumam
  ser abstratas ("a nossa evolução deixou de ser genética e passou a ser
  cultural") — difíceis de visualizar diretamente, e frases de tom
  declarativo/citável alimentam o bug de texto borrado (ver gotcha em
  `gerar_imagens.py` abaixo). Reescrever cada frase numa cena concreta
  (sujeito, ação, cenário, iluminação) antes de mandar pro ComfyUI dá
  imagem melhor e evita esse gatilho. Escrever uma entrada por frase do
  `<nome>_manifesto.json` (mesma numeração 1-based); frase sem entrada cai
  no texto literal.

- **`<nome>` nos arquivos gerados vem do nome do roteiro usado NA GERAÇÃO**
  (`Path(manifesto["roteiro"]).stem`), não precisa bater com `texto.md` —
  o campo `roteiro` de um manifesto antigo pode inclusive apontar pra um
  caminho que não existe mais (ex.: uma cópia temporária tipo
  `humanidade_masculino.md` usada só pra gerar_video.py não sobrescrever o
  áudio de outra voz); isso não quebra nada porque só o `.stem` importa pra
  nomear arquivo, e o texto completo já fica salvo em `texto_usado` dentro
  do próprio manifesto. Depois de gerado, o roteiro fonte pode ser
  arquivado/renomeado pra `texto.md` sem precisar regerar nada.
- **Roteiro longo (> ~1min de fala) vira série, uma pasta por parte, todas
  dentro do mesmo `Video_N/`**: `Projetos/Video_N/<nome-do-projeto>_parte2/`,
  `_parte3/`, ... (a primeira parte fica na pasta sem sufixo, ex.:
  `Video_1/historia_humanidade/` = parte 1). Cada pasta de parte é um
  projeto completo e independente nessa convenção (seu
  próprio `texto.md`/`vozes.md`/manifestos/`imagens/`/`video/`), não uma
  subpasta. `gerar_video.py` não corta/agrupa nada — sintetiza o `texto.md`
  de cada pasta exatamente como está; por isso o roteiro precisa ser
  pré-dividido à mão em blocos de ~130-140 palavras (mesma faixa de taxa de
  fala já medida no projeto) ANTES de gerar áudio, um `texto.md` por pasta
  de parte. Isso também garante que todas as vozes usem exatamente o mesmo
  texto por parte (testar uma voz mais rápida ou mais lenta não muda onde o
  texto é cortado, porque o corte não depende mais de taxa medida).
- **Um só `_imagens_manifesto.json` por projeto, não um por voz**: como as
  imagens são geradas a partir do texto de cada frase (não da voz),
  manifestos de imagem de vozes diferentes do mesmo roteiro saem idênticos
  — gerar mais de um é puro desperdício. Ao testar uma voz nova do mesmo
  texto, aponte `montar_video.py --imagens-nome <nome-original>` pro
  prefixo das imagens já existentes em vez de duplicar `.png` ou o
  manifesto de imagens (ver flag em `montar_video.py` abaixo).
- **Os `.wav` intermediários (`audio/`, `samples_vozes/`) não precisam
  sobreviver depois do `.mp4` final** — o áudio já fica embutido em
  `video/*.mp4`. Isso economiza bastante espaço (WAV não comprimido é
  grande, e um teste de vozes pode gerar dezenas de samples), mas tem uma
  pegadinha: **sem o `.wav`, não dá pra re-rodar só `montar_video.py`** pra
  ajustar legenda/zoom/proporção — teria que rodar `gerar_video.py` de novo
  primeiro. E como o XTTS-v2 não usa seed fixa, resintetizar não reproduz o
  mesmo áudio nem os mesmos timestamps por frase (ficam parecidos, não
  idênticos) — na prática isso gera um manifesto novo, não uma continuação
  do antigo. Se ainda estiver iterando na legenda/zoom de uma parte (como
  fizemos nesta sessão, várias rodadas só de `montar_video.py`), segure a
  limpeza dos `.wav` até fechar esse ajuste.

## Automação: `scripts/gerar_video.py`

Sintetiza um roteiro de texto único (exatamente como está no arquivo, sem
cortar em blocos) usando o servidor local via HTTP.

```powershell
# com o servidor já rodando (uvicorn server.main:app --port 8011)
.\venv\Scripts\python.exe scripts\gerar_video.py Projetos\Video_1\historia_humanidade\texto.md
# voz feminina só se pedida explicitamente:
.\venv\Scripts\python.exe scripts\gerar_video.py Projetos\Video_1\historia_humanidade\texto.md --voz "Ana Florence"
```

- Saída em `<pasta-do-roteiro>/audio/<nome>.wav`, mais um
  `<nome>_manifesto.json` com texto, aviso de normalização, duração e
  timestamps por frase.
- **Voz padrão é `"Dionisio Schuyler"` (masculina)** — `--voz` só precisa
  ser passado pra gerar a versão feminina (`"Ana Florence"`) ou testar outro
  locutor embutido/clonado (`"custom:<arquivo>.wav"`).
- **Velocidade padrão é `1.20`** (`--velocidade`, speed nativo do XTTS-v2,
  ver `tts_engine.py` acima) — escolhida ouvindo amostras de 0.85 a 1.30 lado
  a lado no mesmo texto/voz (ver `Projetos/testes_velocidade/`); `--velocidade
  1.0` volta pro ritmo "neutro" do modelo. Gravado no manifesto (`velocidade`)
  pra saber depois com que cadência cada áudio foi gerado.
- Por padrão `--normalizar` fica desligado (mesmo padrão do checkbox do
  front): a normalização via Ollama é opt-in.
- Não agrupa/corta o texto em blocos de ~1 min — isso é responsabilidade de
  quem escreve o `texto.md` de cada parte (ver "Roteiro longo vira série"
  na convenção de pastas acima). Um roteiro `.md` = um `.wav`.

## Automação: `scripts/gerar_imagens.py`

Gera uma imagem de fundo por FRASE (não por parte inteira — muito mais
dinâmico no vídeo final), usando os timestamps por frase que
`gerar_video.py` já calculou (lê o `<nome>_manifesto.json`, não o roteiro
bruto).

```powershell
# com o ComfyUI Desktop aberto (API em 127.0.0.1:8188)
.\venv\Scripts\python.exe scripts\gerar_imagens.py Projetos\Video_1\historia_humanidade\texto_manifesto.json --prompts Projetos\Video_1\historia_humanidade\texto_prompts.json
# regerar só frases específicas (ex.: depois de revisar e achar 2 ruins)
.\venv\Scripts\python.exe scripts\gerar_imagens.py Projetos\Video_1\historia_humanidade\texto_manifesto.json --prompts Projetos\Video_1\historia_humanidade\texto_prompts.json --frases 2,6
```

- Saída em `<projeto>/imagens/<nome>_FF.png` (FF = frase), mais um
  `<nome>_imagens_manifesto.json` (mescla com o que já existia — regerar só
  algumas frases com `--frases` não apaga o registro das outras).
- **`--prompts <arquivo>.json`**: usa `{"<frase>": "descrição visual"}`
  (ver `texto_prompts.json` na convenção de pastas acima) como prompt em
  vez do texto literal da narração daquela frase — frase sem entrada no
  arquivo cai no texto literal. **Sempre escreva esse arquivo à mão antes
  de gerar imagens** (reescrevendo cada frase numa cena concreta em
  inglês, não traduzindo/parafraseando frase por frase mecanicamente): o
  texto literal da narração costuma ser abstrato demais pra virar uma boa
  cena visual direto, e frases de tom declarativo/citável disparam o bug
  de texto borrado (ver logo abaixo).
  **Escreva sempre em inglês, nunca misture idioma dentro do mesmo
  prompt**: `_SUFIXO_SEGURANCA` é apensado em inglês a qualquer seed —
  um seed em português (ou qualquer mistura de idiomas) desestabiliza o
  refino (`qwen3vl_4b`, modelo pequeno) e pode fazer ele ecoar fragmentos
  garranchados das próprias regras do system prompt como texto visível na
  imagem (ver GOTCHAS.md item 7).
- **Depois de gerar, abra e confira CADA imagem antes de rodar
  `montar_video.py`** — não é opcional. Além do texto garranchado acima,
  o modelo de difusão às vezes ignora o prompt inteiro e desenha algo
  completamente fora do tema (já reproduzido: personagem estilo anime em
  roupa reveladora, sem qualquer gatilho óbvio no prompt) — o script
  termina sem erro nos dois casos, "rodou sem erro" não é sinal de "saiu
  certo". Se uma frase quebrar 2x seguidas com o mesmo prompt, pare de só
  regenerar (seed novo nem sempre resolve) e reescreva o texto do prompt
  daquela frase — ver GOTCHAS.md item 8.
- **Sempre grava o prompt de cada imagem gerada no Krea**: cada entrada do
  `<nome>_imagens_manifesto.json` inclui `prompt_final` (o texto exato
  enviado pro node de prompt do ComfyUI — frase + `_SUFIXO_SEGURANCA`, sem o
  refino do `TextGenerate`) e `arquivo_comfy` (o nome que o próprio ComfyUI
  deu ao arquivo, útil pra cruzar com o histórico da UI). Não é log
  incidental: é o único jeito de saber depois qual prompt gerou qual
  imagem — essencial pra revisar, reproduzir ou ajustar uma imagem
  específica sem ter que re-deduzir o prompt a partir da frase. Preserve
  esses dois campos em qualquer refactor de `gerar_imagens.py`.
- Formato `9:16 (Portrait Widescreen)` por padrão (`--aspect-ratio`) — vídeo
  curto é pensado pra celular; ver gotcha abaixo sobre confiabilidade desse
  formato nesse modelo.
- Sempre liga `Refine Prompt` (node `30:24`) no workflow: deixa o
  `TextGenerate` do próprio ComfyUI (usa o `qwen3vl_4b` já carregado como
  LLM) expandir a frase numa descrição visual mais rica. Testado mandando a
  frase em português puro — o refino manteve o idioma e ficou coerente,
  então não precisa de um passo de tradução via Ollama à parte.
- **Prompt final curto (`_REGRA_PROMPT_CURTO`)**: a regra 2 do system
  prompt original do refino ("Practical T2I Structure") incentiva um
  parágrafo rico com vários detalhes simultâneos — observado que isso
  aumenta a taxa de alucinação (painéis duplicados, enquadramento
  rotacionado, membros extras) especificamente em formatos
  verticais/retrato (os usados pra celular, ver gotcha logo abaixo). Regra
  extra apensada (mesmo mecanismo de `_REGRA_SEM_TEXTO`) pedindo um prompt
  final de no máximo ~40 palavras. Combina bem com `--prompts` (acima): um
  seed já curto e concreto tende a só ser "polido" pela regra 7 do system
  prompt original (que pede pra não expandir demais um input já detalhado)
  em vez de virar um parágrafo longo.
- **Guarda-corpo de nudez (`_SUFIXO_SEGURANCA`)**: por padrão o
  `krea2_turbo` desenha figuras humanas nuas quando o prompt não menciona
  vestimenta — mesmo a regra 8 do system prompt do workflow ("assuma roupa
  cobrindo anatomia íntima") não evita isso sozinha, porque a regra 5 do
  mesmo system prompt instrui o refino a não inventar detalhe de vestuário
  que o input não sustenta. Testei desconectar o node
  `ConditioningKrea2Rebalance` da saída positiva do `KSampler` (achando que
  fosse um parâmetro de "descensura") e não resolveu — só reduziu o quão
  explícita a nudez saía. A correção que funciona é declarar vestimenta
  explicitamente no prompt (`_SUFIXO_SEGURANCA`, aplicado a toda geração em
  `montar_prompt()`), o que aciona a regra 1 (preservar o que o input já diz)
  em vez de esbarrar na regra 5. Mesmo com isso, trate a saída como
  rascunho — revise as imagens antes de usar no vídeo final.
- **Formato vertical nativo (9:16) é bem menos confiável que 16:9 nesse
  modelo/LoRA**: gerando as 9 frases de um teste direto em
  `9:16 (Portrait Widescreen)`, 6 de 9 saíram com defeito (4 rotacionadas
  90°, 1 tríptico de 3 painéis, 1 com texto borrado) — bem mais que a taxa
  vista em 16:9. Se for reconsiderar voltar pra gerar em 16:9 + recorte no
  ffmpeg (jeito antigo, mais confiável, ver histórico do
  `montar_video.py`), essa é a razão.
- **Texto borrado na imagem (causa raiz e correção, `_REGRA_SEM_TEXTO`)**:
  o `TextGenerate` (refino de prompt) tem seu próprio system prompt com uma
  regra 4 ("se o usuário pedir texto visível, coloque entre aspas") — pra
  frases de narração que soam como uma citação fechada (tom declarativo,
  termina em ponto), o refino decide sozinho que aquilo é "texto pra
  mostrar na tela" e cita a frase (às vezes até o nosso próprio
  `_SUFIXO_SEGURANCA`) como legenda; o modelo de difusão então tenta
  desenhar essas letras e sai borrado/ilegível (confirmado lendo o texto
  borrado — em várias imagens reproduzia a frase de entrada quase
  literalmente, incluindo nosso sufixo). **O que NÃO resolveu sozinho**:
  regenerar só com seed novo do `KSampler` (`30:3`) — o node de refino
  (`30:16`) tem `sampling_mode.seed` fixo em `0` no workflow, então pra uma
  mesma frase de entrada ele produz sempre a mesma descrição (e o mesmo
  defeito) não importa quantas vezes troquemos o seed da difusão; testei
  isso explicitamente (regenerei 6 imagens quebradas só com seed novo, só
  1 saiu corrigida). Encurtar `_SUFIXO_SEGURANCA` (de uma frase inteira pra
  um fragmento curto) ajudou em alguns casos mas não em todos. **O que
  resolveu**: apensar uma regra extra ao system prompt do refino
  (`_REGRA_SEM_TEXTO`, aplicada só na cópia do workflow que enviamos —
  não mexe no arquivo salvo em `comfy/`) proibindo explicitamente renderizar
  o input (ou paráfrase/citação dele) como texto visível. Depois dessa
  regra, todas as frases que ainda estavam quebradas saíram limpas.
- Timing observado é bem instável: 60s numa geração, 362s noutra com o
  mesmo workflow/config (só o `KSampler`+`VAEDecode` reexecutaram, o resto
  veio do cache do ComfyUI) — GPU a 7-8% de uso o tempo todo, não
  parece ser gargalo de computação. Não isolei a causa raiz; confirmei que
  não é disputa de VRAM com o XTTS-v2 (checar processos com `nvidia-smi
  --query-compute-apps=pid,process_name,used_memory --format=csv` — só o
  `python.exe` do ComfyUI aparecia como processo de cômputo). Reinstâncias
  do ComfyUI Desktop parecem "curar" períodos de lentidão (o timing voltou
  a ficar consistente em ~60-90s/imagem depois de reiniciar o app no meio
  de uma sessão de testes), mas não confirmei causalidade. Se for
  investigar mais, rode várias gerações seguidas com o mesmo prompt/seed e
  compare os tempos antes de mexer em configuração.
- Ao cancelar o script no meio de uma geração, o job que já estava
  `queue_running` no ComfyUI pode continuar rodando (não é abortado
  automaticamente) — chamar `POST /interrupt` na API do ComfyUI ajuda, mas
  não é imediato se o job estiver preso numa etapa do `TextGenerate` (LLM),
  que parece não checar o cancelamento tão granularmente quanto o
  `KSampler`. Na pior hipótese ele só termina sozinho gerando uma imagem
  que ninguém usa — sem problema, só não espere um cancelamento instantâneo.

## Automação: `scripts/montar_video.py`

Junta uma imagem por frase (cada uma com seu próprio zoom) + áudio +
legenda num `.mp4` final, via `ffmpeg` (precisa estar no PATH — não é
dependência Python).

```powershell
python scripts\montar_video.py Projetos\Video_1\historia_humanidade\texto_manifesto.json
# reaproveitando as imagens de outra voz do mesmo roteiro (sem duplicar .png)
python scripts\montar_video.py Projetos\Video_1\historia_humanidade\texto_feminino_manifesto.json --imagens-nome texto
```

- Lê `frases` (timestamps por frase) do manifesto de `gerar_video.py` e as
  imagens de cada frase de `gerar_imagens.py` (`imagens/<nome>_FF.png`,
  uma por frase — precisa ter sido gerada uma pra cada frase, o script erra
  com uma mensagem clara e o comando pra completar se faltar alguma). Se o
  manifesto não tiver `frases` (gerado antes dessa timing existir), o
  script pede pra rodar `gerar_video.py` de novo em vez de tentar adivinhar.
- Saída em `<projeto>/video/<nome>_<proporção>.mp4`.
- **`--imagens-nome`**: por padrão o prefixo das imagens é derivado do
  `roteiro` gravado no manifesto (`Path(manifesto["roteiro"]).stem`) — o
  mesmo prefixo que `gerar_imagens.py` usa ao salvar. Testar o mesmo roteiro
  com vozes diferentes normalmente exige gerar um manifesto próprio pra cada
  voz (pra não sobrescrever o áudio de uma versão anterior), o que muda esse
  prefixo mesmo as frases/imagens sendo idênticas — sem essa flag, a saída
  seria duplicar os `.png` só pra bater o nome esperado. Com
  `--imagens-nome <prefixo-original>`, aponta pra reaproveitar os arquivos
  de imagem já existentes de outra voz/manifesto do mesmo roteiro, sem
  copiar nada.
- **Um clipe por frase, concatenados**: como cada frase já tem sua própria
  imagem (gerada por `gerar_imagens.py`, ver acima), `montar()` renderiza
  um clipe mudo por frase (`renderizar_clipe_imagem()`) e concatena tudo
  via `ffmpeg -f concat` (stream copy, sem recodificar) antes de somar
  áudio+legenda numa segunda passada. Cada clipe cobre do início da sua
  frase até o início da próxima (não só a duração da fala) — inclui a
  pausa entre frases, senão a soma das durações dos clipes fica menor que
  o áudio e desalinha tudo.
- **Efeito de movimento é zoom, não pan**: como as imagens já nascem no
  formato vertical final (sem folga lateral), o `pan` usado numa versão
  anterior (quando as imagens eram geradas em 16:9) não faz mais sentido —
  não sobra largura pra deslizar. `renderizar_clipe_imagem()` usa
  `zoompan` do ffmpeg com interpolação linear em função do frame (`on`),
  não o incremento recursivo padrão (`zoom+0.001` etc.) — isso é o que
  permite bater exatamente a duração pedida por frase, que varia. Direção
  (`zoom-in`/`zoom-out`) alterna a cada frase por padrão (`--efeito
  alternar`) pra variar o movimento entre uma imagem e outra. Testado
  isoladamente com frames extraídos do início/fim do clipe antes de
  integrar no pipeline — validar visualmente qualquer filtro novo do
  ffmpeg assim antes de confiar nele, ver gotcha do `original_size` abaixo
  pra um exemplo de quanto um filtro pode enganar sem gerar nenhum erro.
  **Tremor no zoom**: com a imagem de entrada perto do tamanho final
  (768x1368 do ComfyUI pra uma saída de 1080x1920), o `zoompan` recalcula a
  janela de corte em pixels inteiros a cada frame, e esse arredondamento é
  uma fração grande do deslocamento entre frames — o zoom sai visivelmente
  tremido. Fix padrão (bem documentado, não é invenção nossa): escalar a
  imagem pra bem maior que o final ANTES do `zoompan` (`_SUPERSAMPLE = 4`,
  ou seja 4320x7680 pra uma saída de 1080x1920), deixando o `s=` do próprio
  `zoompan` reamostrar pra baixo no final — o mesmo arredondamento de pixel
  inteiro vira uma fração desprezível numa imagem 4x maior. Não tem como
  validar "tremor" olhando frames extraídos isolados (é um efeito de
  movimento, só aparece reproduzindo o vídeo) — se voltar a acontecer
  depois de alguma mudança, aumentar `_SUPERSAMPLE` é o primeiro lugar pra
  mexer.
- **Legendas são subdivididas, não uma por frase**: uma frase inteira como
  legenda única fica grande demais/lenta demais num vídeo vertical (chegou
  a ocupar a tela toda em frases de 20+ palavras). `dividir_em_legendas()`
  quebra cada frase em pedaços de até 4 palavras (`_PALAVRAS_POR_LEGENDA`,
  no padrão de legenda curta de conteúdo pra celular — sem quebra de linha,
  centralizada no meio do vídeo em vez de perto do rodapé), interpolando o
  tempo de cada pedaço proporcionalmente à contagem de palavras dentro do
  intervalo conhecido da frase (não é medição real — o motor só dá
  timestamp por frase, não por palavra; aproximação assume ritmo de fala
  ~constante dentro da frase).
- **Legenda é `.ass` escrito à mão (`gerar_ass()`), não `.srt` + filtro
  `subtitles`**: a primeira versão gerava um `.srt` e usava
  `subtitles=legenda.srt:original_size=WxH:force_style='...'`. Na conversão
  interna que o filtro `subtitles` faz de SRT pra ASS, o tamanho de fonte e
  o alinhamento do `force_style` saíram completamente errados — texto ~6x
  maior que o `FontSize` pedido e grudado no topo mesmo com
  `Alignment=5` (meio-centro), mesmo com `original_size` batendo
  corretamente com a resolução do vídeo (ver gotcha de `original_size`
  logo abaixo — aquele problema é outro, já resolvido antes, e não foi a
  causa desse). Confirmado extraindo frame do `.mp4` renderizado e
  comparando visualmente (`ffmpeg -ss <t> -frames:v 1 saida.png`) — o
  tamanho/posição real não tinha relação óbvia com os valores pedidos, sinal
  de que o `PlayResY` assumido pela conversão SRT→ASS não estava batendo
  com a resolução real do vídeo. A correção foi abandonar `subtitles` +
  `force_style` e escrever o `.ass` diretamente com `PlayResX`/`PlayResY`
  = `largura`/`altura` de saída (elimina qualquer fator de escala
  implícito) e `WrapStyle: 2` no `[Script Info]` (desliga quebra de linha
  automática — junto com o limite de 4 palavras por legenda, garante uma
  linha só). O filtro final é só `ass=legenda.ass`, sem `force_style` nem
  `original_size`.
- **Gotcha do ffmpeg (histórico, filtro `subtitles`, não mais usado
  aqui)**: o filtro `subtitles` (`force_style=...:original_size=WxH`)
  espera em `original_size` o tamanho do frame de **entrada do
  filtergraph** (o vídeo antes de qualquer `scale`/`crop` que rode ANTES do
  `subtitles` na mesma cadeia) — não o tamanho final pós-crop, apesar do
  nome e da posição do parâmetro sugerirem isso. Passar o tamanho errado
  ali faz o libass calcular a escala errada, e isso acontece
  *silenciosamente*, sem warning no log do ffmpeg (`-loglevel verbose`
  mostra o "Setting force_style to value..." confirmando que a opção foi
  lida, então o instinto de "será que não tá sendo aplicada" é um beco sem
  saída). Deixou de ser relevante pra `montar_video.py` depois da mudança
  pra `.ass` escrito à mão (ponto acima), mas fica registrado caso
  `subtitles`+`force_style` seja usado em outro lugar do repositório: meça
  o tamanho de entrada real (`ffprobe`) em vez de assumir.

## Automação: `scripts/gerar_capa.py`

**Passo final de todo vídeo** — sem capa, o projeto não está pronto pra
postar. Gera uma cena NOVA e chamativa no ComfyUI a partir de um `--prompt`
escrito à mão e desenha o título por cima como texto real (Pillow), não
pedindo pro modelo de difusão desenhar o texto — mesmo raciocínio do
`_REGRA_SEM_TEXTO` em `gerar_imagens.py`: diffusion model é ruim em texto,
sai borrado/ilegível.

**A capa nunca reaproveita uma imagem de `imagens/`** (as usadas no corpo
do vídeo): aquelas são pensadas pra ilustrar a frase que está sendo narrada
naquele momento, não pra vender o vídeo pra quem está rolando o feed. O
`--prompt` da capa deve ser escrito com esse objetivo em mente — uma cena
mais dramática/impactante que qualquer frase isolada do roteiro, seguindo a
mesma lógica de "escrever à mão em inglês" de `texto_prompts.json` (ver
`gerar_imagens.py` acima e seus gotchas de prompt).

```powershell
python scripts\gerar_capa.py Projetos\Video_1\historia_humanidade_parte2\texto_manifesto.json --prompt "dramatic wide shot of a meteor impact lighting up a prehistoric sky, cinematic, high contrast"
# título explícito em vez de ler a 1a linha de descricao.md
python scripts\gerar_capa.py Projetos\Video_1\historia_humanidade_parte2\texto_manifesto.json --prompt "..." --titulo "História da Humanidade — Parte 2/5"
# reaproveitando um capa_fundo.png já gerado antes (só reajusta o título, não chama o ComfyUI de novo)
python scripts\gerar_capa.py Projetos\Video_1\historia_humanidade_parte2\texto_manifesto.json --imagem Projetos\Video_1\historia_humanidade_parte2\capa_fundo.png
```

- `--prompt` é obrigatório a menos que `--imagem` seja passado — o script
  falha com uma mensagem clara em vez de silenciosamente cair de volta pra
  reaproveitar uma imagem de `imagens/` (essa era a lógica antiga; foi
  removida de propósito, ver acima).
- Geração do fundo reusa `gerar_imagem()` de `gerar_imagens.py` (mesmo
  workflow Krea2, mesmo `_SUFIXO_SEGURANCA`/`_REGRA_SEM_TEXTO` aplicados
  automaticamente) — precisa do ComfyUI Desktop aberto (API em
  `127.0.0.1:8188`), exceto quando `--imagem` é usado.
- Sem `--titulo`, usa a 1ª linha de `<projeto>/descricao.md` (sem o "👇"
  final) — já é exatamente o título+indicador de parte que a legenda usa,
  então não precisa digitar de novo.
- Composição do texto: cobre (`background-size: cover`, sem esticar) o
  fundo gerado pro tamanho final, escurece a parte de baixo em gradiente
  (fica legível em cima de qualquer imagem, não só pelo contorno preto do
  texto) e desenha o título em branco com contorno preto, mesma família
  (Arial Bold) usada na legenda do vídeo. Fonte reduz automaticamente até
  caber na largura/altura reservadas — título longo quebra em mais linhas
  ou encolhe, não estoura o quadro.
- Saída: `<projeto>/capa_fundo.png` (cena gerada, sem texto — reaproveitável
  via `--imagem` se só o título mudar), `<projeto>/capa_manifesto.json`
  (`prompt_final`/`arquivo_comfy`, mesma lógica de rastreabilidade do
  `_imagens_manifesto.json`: é o único jeito de saber depois qual prompt
  gerou a capa) e `<projeto>/capa.png` (resultado final, com título). Não
  depende de voz/manifesto de áudio — testar outra voz do mesmo roteiro não
  precisa gerar capa de novo.

## Gotchas

- O checkpoint do XTTS-v2 (~1.8GB) baixa do Hugging Face no primeiro uso —
  primeira chamada a `/api/synthesize` (ou `/api/voices`, que já instancia o
  engine) é lenta e precisa de internet.
- `voice_id` no formato `"custom:<arquivo>.wav"` usa clonagem via
  `speaker_wav`; qualquer outro valor é tratado como nome de locutor embutido
  do XTTS-v2 (`speaker=`). Ver `TTSEngine.synthesize` em `tts_engine.py`.
- `TTSEngine.synthesize()` retorna `(output_path, frases)` — `frases` é uma
  lista de `{texto, inicio_s, fim_s}` por sentença, calculada durante a
  própria concatenação do áudio (a gente já sabe onde cada frase começa e
  termina porque foi a gente quem montou o clipe, frase por frase — não
  precisa de um passo de transcrição/alinhamento à parte pra gerar
  legenda). `POST /api/synthesize` expõe isso no campo `frases` da
  resposta; `gerar_video.py` persiste no manifesto. Ver `montar_video.py`
  pra como isso vira `.srt`.
- **Race condition no singleton do engine** (já corrigida, mas fácil de
  reintroduzir se mexer em `get_tts_engine()`): rotas síncronas do FastAPI
  (como `GET /api/voices`) rodam numa thread pool; sem lock, requests
  concorrentes que chegam antes de `_engine` ser setado disparam múltiplas
  construções de `TTSEngine()` em paralelo. Reproduzido na prática por um
  client fazendo poll agressivo em `/api/voices` durante a subida do
  servidor — gerou ~40 tentativas concorrentes de carregar o XTTS-v2.
  `get_tts_engine()` agora usa double-checked locking (`_engine_lock`) pra
  evitar isso.
- Sem HTTPS/SSL (diferente do karaoke) — este servidor não captura microfone,
  então não precisa de contexto seguro; HTTP simples em `127.0.0.1:8011` basta.
- **Bug conhecido do XTTS-v2 em português**: o modelo às vezes verbaliza "."
  como a palavra "ponto" em vez de tratá-lo como pausa
  ([coqui-ai/TTS#2952](https://github.com/coqui-ai/TTS/issues/2952), sem fix
  oficial). Mitigado em `tts_engine.py` (`_sanitizar_pontuacao_pt`): troca
  pontos finais por `|` antes de sintetizar em pt (preserva números decimais
  como "3.14"). Só ataca esse bug específico, não é uma correção do modelo.
  **Importante**: a troca só pode acontecer DEPOIS que o texto já foi dividido
  em frases via `self.tts.synthesizer.split_into_sentences(text)` (pysbd, que
  usa o ponto pra achar os limites de frase). Se a troca acontecesse antes da
  divisão, o texto inteiro vira uma única "frase" sem pontos pra dividir, e
  textos longos estouram o limite de 400 tokens do XTTS-v2 (`❗ XTTS can only
  generate text with a maximum of 400 tokens`). Por isso `TTSEngine.synthesize`
  sintetiza frase por frase (`split_sentences=False` por chamada) e concatena
  o áudio manualmente com `numpy`, em vez de passar o texto inteiro pro
  `tts_to_file` de uma vez.
  **Pausas entre frases**: cada frase sintetizada isoladamente já vem com
  silêncio próprio de abertura/fechamento; concatenar sem tratar isso faz o
  silêncio nativo somar com qualquer gap adicionado, ficando artificialmente
  longo e "mudo" (medido: 0.82s, contra ~0.55s de uma pausa natural de "."
  numa única chamada contínua). `_trim_silencio` apara esse silêncio de cada
  clipe (limiar de RMS) antes de somar `_GAP_ENTRE_FRASES_S` (0.35s, ajustado
  empiricamente pra soar próximo do natural).
  **Cuidado ao cortar rente**: aparar exatamente no ponto onde o RMS cruza o
  limiar corta o fim da frase de forma abrupta (soa como a fala foi cortada,
  mesmo sem remover fonemas de fato — o problema é a transição brusca pro
  silêncio, não perda de conteúdo). `_trim_silencio` por isso mantém uma
  margem (`_MARGEM_TRIM_S`, 80ms) além do limiar e aplica um fade-in/fade-out
  curto (`_FADE_S`, 30ms) nas bordas do clipe cortado. Se for mexer nesses
  números, meça com RMS por janela (script usado: gerar o clipe, calcular RMS
  em janelas de 20ms, olhar os valores perto do ponto de corte) em vez de
  julgar de ouvido.
- **XTTS-v2 "trava"/alonga demais em frases com datas compostas** (ex.: "Roma,
  26 de abril de 121 – Vindobona, 17 de março de 180"): uma frase que deveria
  durar ~5s saiu com 14-17s (repetição/alucinação do decoder autoregressivo).
  Isolei a causa testando várias variantes (ver conversa) — **não é parêntese
  nem travessão** (removendo cada um separadamente o problema persistiu) e
  **não é resolvido escrevendo os números por extenso**. O gatilho parece ser
  especificamente **duas expressões "dia de mês de ano" completas na mesma
  frase** (nascimento + morte); com só um número/data por frase (mesmo cru,
  em dígitos) a duração fica normal. Sem correção automática implementada —
  o workaround é reescrever esse tipo de frase biográfica quebrando em duas
  (ex.: "X nasceu em Roma em 26 de abril de 121. Morreu em Vindobona em 17 de
  março de 180."), já que datas compostas desse jeito são raras no uso comum
  da plataforma. Não é bug de uma voz específica — é o texto, reproduz com
  qualquer locutor.
- **`torch.cuda.mem_get_info()` não é confiável no Windows/WDDM para medir
  VRAM entre processos** — chegou a reportar 11GB livres quando só havia 4GB
  de verdade (o Ollama, rodando em processo separado, não aparece na conta do
  PyTorch). Por isso `text_preprocessor._free_vram_mb()` usa `nvidia-smi`
  via subprocess, não `torch.cuda.mem_get_info()`. Se for medir VRAM em
  outro lugar do código, replique essa abordagem em vez de confiar no torch.
- O toggle "Normalizar" no front (`normalizarEl`) é a fonte da verdade: só
  quando marcado o backend sequer tenta chamar o Ollama. O contador de
  tokens (`#contador-tokens`) só aparece com o toggle marcado, usa
  `ollama_num_ctx` retornado por `/api/voices` como referência, e é uma
  estimativa grosseira (~4 caracteres/token) — não reflete o `num_ctx`
  real escolhido no momento da síntese, que é recalculado a cada chamada.
- **Pontuação sozinha NÃO alonga a frase final de forma confiável** (testado
  ao investigar um pedido de "entonação final" mais alongada na última frase
  do vídeo/série): sintetizei a mesma frase de fechamento variando só a
  pontuação final (`.` vs `...` vs `!` vs `—`), 5 repetições por variante,
  medindo a duração pós-`_trim_silencio` (script isolado direto em
  `TTSEngine`, fora do pipeline HTTP). Resultado: `ponto_normal` média
  8.400s (desvio padrão 0.927s), `exclamacao` média 8.788s (desvio padrão
  0.940s), `reticencias` média 8.400s (desvio padrão 0.458s) — a diferença
  entre pontuações (~0.4s) é bem menor que a variância natural do próprio
  XTTS-v2 de uma síntese pra outra (o modelo não usa seed fixa, ver gotcha
  de `.wav` intermediários acima). Ou seja, o "efeito" que aparece rodando
  uma síntese só por variante é ruído de amostragem, não um sinal real de
  pontuação controlando cadência/entonação. **Se essa entonação final for
  retomada no futuro**, pontuação não é o caminho — a única alavanca real
  que já existe no motor é o `speed` nativo do XTTS-v2 (`tts_engine.py`),
  que hoje só é aplicado uniformemente pra frase inteira sintetizada por
  chamada; alongar só a última frase exigiria sintetizá-la separadamente
  com um `speed` menor que o resto (mudança de código, não testada ainda).
