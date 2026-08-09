# Plano: continuidade de personagem (opcional) em `gerar_imagens.py`

> **Este documento é autocontido.** Foi escrito pra ser executado por uma
> sessão nova do Claude Code, sem acesso à conversa que o originou. Leia
> este arquivo inteiro antes de tocar em código — ele já traz o contexto,
> a investigação técnica e o design aprovado pelo usuário; não é um
> rascunho pra ser redesenhado do zero.
>
> **Antes de começar, leia também** [CLAUDE.md](CLAUDE.md) deste
> subprojeto (arquitetura geral, convenções de pasta, regras de código) e
> [comfy/GOTCHAS.md](comfy/GOTCHAS.md) (defeitos já catalogados do
> pipeline de geração de imagem — nudez, texto borrado, formato 9:16
> instável, desvio de tema). Ambos têm o mesmo estilo de documentação que
> este arquivo tenta seguir: rationale + gotchas testados, não só "como
> usar".
>
> Depois de implementar, siga o fluxo Git obrigatório do repositório
> (commit descritivo + push imediato — ver `CLAUDE.md` da raiz do repo
> `Ferramentas`), commitando só os arquivos relacionados a esta feature
> (não misture com outro trabalho em progresso que porventura já esteja
> sujo no working tree).

## Contexto

`scripts/gerar_imagens.py` gera uma imagem de fundo por frase de um
roteiro de vídeo curto, via ComfyUI local (`http://127.0.0.1:8188`). Cada
chamada é um txt2img totalmente independente — nenhuma referência entre
gerações. Quando um roteiro tem um personagem recorrente, a aparência dele
deriva de frase pra frase.

Isso foi observado ao vivo no projeto `Projetos/Video_9/` (mito de
Prometeu, já produzido e commitado nesta plataforma — ver
`Projetos/Video_9/analise.md`... **correção**: o arquivo de análise do
modelo de imagem fica em `analise.md` na raiz deste subprojeto, não dentro
da pasta do projeto; o caso específico está documentado lá, seção "2.
Moderado — deriva de identidade/estilo entre imagens da mesma
'personagem'"). Resumo do caso: na frase 7 do roteiro (Prometeu
acorrentado, sendo atacado pela águia) saiu um homem loiro de cabelo
comprido, capa verde-escura aberta expondo o peito; na frase 8 (mesma
"cena", continuação direta — o fígado se regenerando à noite), o mesmo
personagem saiu como uma pessoa em trajes tradicionais asiáticos, sem
nenhuma relação visual com a frase anterior. O fix aplicado na hora foi
100% manual: reescrever o prompt da frase 8 repetindo os descritores
físicos já estabelecidos na frase 7 (loiro, capa verde aberta). Funcionou
pontualmente, mas não escala pra roteiros com um personagem em muitas
frases, e não dá nenhuma garantia real de identidade — é só "insistir com
palavras" pro modelo, que pode ou não obedecer.

O usuário pediu um mecanismo melhor pra isso — **aceita que seja
trabalhoso, desde que fique 100% opcional**. A maioria dos vídeos desta
plataforma NÃO tem um personagem único recorrente nas imagens (são cenas
soltas ilustrando cada frase da narração), então esse mecanismo não pode
adicionar custo nem complexidade ao caminho padrão (gerar imagens sem
nenhuma flag nova = comportamento idêntico ao de hoje).

## Investigação já feita (não repetir do zero)

**Modelo de imagem em uso**: `Z-Image-Turbo`
(`comfy/image_zimage_turbo_t2i.json`), arquitetura **Lumina2** (DiT), 6B
parâmetros, Tongyi-MAI. Roda em poucos steps (8), `cfg=1`, sem prompt
negativo real (usa `ConditioningZeroOut`). É o modelo que substituiu o
`krea2_turbo` antigo (`comfy/image_krea2_turbo_t2i.json`) — trocado porque
o Krea2 tinha uma taxa alta de desviar completamente do prompt e desenhar
personagens estilo anime sem gatilho aparente (ver `comfy/GOTCHAS.md` item
8). `scripts/gerar_imagens.py` já suporta os dois workflows, detectando
qual é qual pela presença do node `"30:24"` no JSON carregado (variável
`eh_krea2` dentro de `gerar_imagem()`).

**Por que não IPAdapter/InstantID**: essas são as ferramentas "padrão" pra
consistência de personagem no ecossistema ComfyUI, mas normalmente são
lançadas (pesos pré-treinados) pra arquiteturas SD1.5/SDXL/FLUX — não há
pesos publicamente confirmados pra Lumina2/Z-Image. Além disso, a
instalação real do ComfyUI Desktop nesta máquina
(`C:\Users\mf827\AppData\Local\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI`)
só tem os custom nodes `ComfyUI-ConditioningKrea2Rebalance` (usado pelo
workflow do Krea2) e `ComfyUI-Manager` instalados — nada de
IPAdapter/InstantID. Adotar essa rota exigiria instalar custom nodes novos
e baixar modelos extras de compatibilidade incerta com esse checkpoint
específico. **Decisão**: evitar essa dependência.

**Abordagem escolhida**: usar só **nodes core do ComfyUI** (`LoadImage`,
`ImageScale`, `VAEEncode` — confirmados como nodes nativos, não custom,
presentes em qualquer instalação do ComfyUI) pra fazer **img2img com
denoise parcial** a partir de uma imagem de referência já gerada. Essa é
uma técnica já documentada publicamente como usada especificamente com o
checkpoint Z-Image-Turbo (buscada como "Z-Image Turbo I2I ... Identity-True
Retouching"), então não é experimental — só precisa ser cabeada no
workflow deste projeto.

**Sobre `denoise` parcial e `steps`**: confirmado lendo
`comfy/samplers.py` (`KSampler.set_steps`) da instalação real do ComfyUI —
o número de iterações reais de sampling executadas é sempre igual ao
valor do widget `steps`, **independente do valor de `denoise`**; o que
`denoise<1` muda é só qual trecho final do cronograma de sigmas é
percorrido (equivalente a "começar com menos ruído"). **Não precisa
aumentar `steps`** quando `denoise<1` — o valor herdado do workflow t2i
(`8`) continua sendo 8 iterações reais mesmo em denoise parcial.

**Sobre `ImageScale` e distorção**: `crop="disabled"` redimensiona a
imagem de referência pro tamanho alvo **sem preservar aspect ratio** (pode
esticar/espremer). `crop="center"` recorta primeiro pro aspect ratio
certo, sem distorção. No fluxo principal esperado (referenciar uma imagem
já gerada no mesmo projeto, mesmo `--aspect-ratio`) os dois são
equivalentes — mas usar `"center"` blinda o caso raro de referenciar uma
imagem de outro projeto/proporção, sem custo no caso comum.

**Rota alternativa mais robusta, descartada por ora**: LoRA por
personagem, via um custom node chamado `Comfyui-ZiT-Lora-loader`
(arquitetura-aware pra Z-Image Turbo/Lumina2, já existe publicamente) +
treino externo (ex. `ai-toolkit`, fora deste repo). Daria identidade mais
fiel e funcionaria mesmo com poses bem diferentes da referência, mas
exige instalar um custom node ainda não presente, curar 15-30 imagens do
personagem e rodar um treino (tempo/VRAM) — esforço bem maior do que o
problema justifica agora. **Não construir isso neste plano** — só deixar
documentado como possível fase futura se o mecanismo de img2img abaixo se
mostrar insuficiente num projeto real.

## Ambiente local (pra rodar/testar)

- Repositório: `c:\Users\mf827\Documents\Ferramentas` (raiz do `.git`);
  este subprojeto vive em `tts_platform_pt/` dentro dele.
- venv: `tts_platform_pt/venv/Scripts/python.exe` já tem as dependências
  (`requirements.txt`) instaladas.
- ComfyUI Desktop precisa estar aberto, API em `http://127.0.0.1:8188`
  (checar com `GET /system_stats` antes de qualquer teste).
- Servidor da plataforma (só necessário se for regerar áudio, não pra
  esta feature): `uvicorn server.main:app --port 8011` de dentro de
  `tts_platform_pt/` com o venv ativado.
- Caso de teste real disponível: `Projetos/Video_9/` (mito de Prometeu, já
  produzido e commitado) — usar as frases 7/8 (deriva documentada) e a
  frase 6/2 (par de pose bem diferente, útil pro teste de caso
  desfavorável) como descrito na seção de verificação abaixo.

## Design técnico aprovado

### 1. Novo workflow: `comfy/image_zimage_turbo_i2i.json`

Cópia de `comfy/image_zimage_turbo_t2i.json`. Grafo atual completo (nodes
`1` a `11`, pra referência exata — **não inventar nomes de node/campo
diferentes destes**):

```json
{
  "1": { "inputs": { "unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default" },
         "class_type": "UNETLoader" },
  "2": { "inputs": { "clip_name": "qwen_3_4b_fp8_mixed.safetensors", "type": "lumina2", "device": "default" },
         "class_type": "CLIPLoader" },
  "3": { "inputs": { "vae_name": "ae.safetensors" }, "class_type": "VAELoader" },
  "4": { "inputs": { "shift": 3, "model": ["1", 0] }, "class_type": "ModelSamplingAuraFlow" },
  "5": { "inputs": { "text": "", "clip": ["2", 0] }, "class_type": "CLIPTextEncode" },
  "6": { "inputs": { "conditioning": ["5", 0] }, "class_type": "ConditioningZeroOut" },
  "7": { "inputs": { "aspect_ratio": "9:16 (Portrait Widescreen)", "megapixels": 1, "multiple": 8 },
         "class_type": "ResolutionSelector" },
  "8": { "inputs": { "width": ["7", 0], "height": ["7", 1], "batch_size": 1 },
         "class_type": "EmptySD3LatentImage" },
  "9": { "inputs": { "seed": 0, "steps": 8, "cfg": 1, "sampler_name": "res_multistep",
                      "scheduler": "simple", "denoise": 1, "model": ["4", 0],
                      "positive": ["5", 0], "negative": ["6", 0], "latent_image": ["8", 0] },
         "class_type": "KSampler" },
  "10": { "inputs": { "samples": ["9", 0], "vae": ["3", 0] }, "class_type": "VAEDecode" },
  "11": { "inputs": { "filename_prefix": "ZImageTurbo", "images": ["10", 0] }, "class_type": "SaveImage" }
}
```

Adicionar 3 nodes novos e modificar o node `9`:

```json
"12": { "inputs": { "image": "" }, "class_type": "LoadImage" },
"13": { "inputs": { "image": ["12", 0], "width": ["7", 0], "height": ["7", 1],
                     "upscale_method": "lanczos", "crop": "center" },
        "class_type": "ImageScale" },
"14": { "inputs": { "pixels": ["13", 0], "vae": ["3", 0] }, "class_type": "VAEEncode" }
```

No node `9`: `"latent_image": ["14", 0]` (era `["8", 0]`); `"denoise"`
deixa de ser fixo em `1` — o script vai sobrescrever esse valor por
chamada (igual já faz hoje com `seed`). O node `8`
(`EmptySD3LatentImage`) pode ficar no JSON mesmo sem uso — o ComfyUI só
executa nós alcançáveis a partir do `SaveImage`, um node órfão não roda e
não custa nada.

`LoadImage.inputs.image` fica como placeholder (`""`) no arquivo salvo —
o script sempre sobrescreve esse valor com o nome retornado pelo upload
antes de mandar o workflow pro ComfyUI (mesmo padrão de `seed` sendo
`0` no JSON salvo e randomizado em runtime).

Depois de criar esse arquivo, teste-o isoladamente ANTES de integrar no
script (ver Fase 2 da verificação, abaixo) — não confie só em leitura de
código pra um grafo do ComfyUI, sempre rode de verdade.

### 2. Mudanças em `scripts/gerar_imagens.py`

Estrutura atual relevante (pra você não precisar redescobrir do zero — mas
leia o arquivo inteiro antes de editar, ele tem ~250 linhas):

- `_NODE_PROMPT`, `_NODE_REFINAR`, etc. = nós do Krea2 (prefixo `"30:"`).
- `_ZIMAGE_NODE_PROMPT = "5"`, `_ZIMAGE_NODE_RESOLUCAO = "7"`,
  `_ZIMAGE_NODE_SAMPLER = "9"`, `_ZIMAGE_NODE_SAVE = "11"` = nós do
  Z-Image t2i atual — **os mesmos IDs valem pro grafo i2i novo** (só
  adiciona nodes `12`/`13`/`14`, não renumera os existentes).
- `montar_prompt(texto)` → `texto.strip() + _SUFIXO_SEGURANCA` — reusar
  sem mudança, o guarda-corpo de nudez/vestimenta continua valendo pro
  branch i2i.
- `gerar_imagem(server, workflow, texto, aspect_ratio, destino, timeout_s=600)`:
  hoje decide entre 2 branches via `eh_krea2 = _NODE_REFINAR in wf`. Isso
  precisa virar uma decisão de **3 branches**: Krea2 t2i (inalterado),
  Z-Image t2i (inalterado, agora o caso "sem referência"), Z-Image i2i
  (novo). A função vai precisar de parâmetros novos pra saber se deve
  usar o branch i2i — ex.: `referencia_imagem: str | None = None` (nome
  de arquivo já enviado ao ComfyUI, não o caminho local) e
  `referencia_denoise: float = 0.5`. **Não decida o branch só pela
  presença de um node no `workflow` recebido** como hoje — quem decide
  se usa i2i é a chamada (se aquela frase tem entrada em `--referencia`),
  não o conteúdo do dict. Isso significa que `main()` precisa passar o
  workflow certo (t2i ou i2i) pra cada chamada, dependendo da frase.
- `main()`: hoje carrega **um** `workflow` (`args.workflow`, default
  Krea2) pra todas as frases da run. Vai precisar também carregar
  `workflow_i2i` — **só se `args.referencia` for passado** (custo zero no
  caminho padrão) — e, dentro do loop de `tarefas`, escolher por frase
  qual dict de workflow usar.
- Padrão de flag existente a espelhar (`--prompts`, já no código):
  ```python
  ap.add_argument("--prompts", type=Path, default=None, help=(...))
  ...
  prompts_custom = {}
  if args.prompts:
      if not args.prompts.exists():
          raise SystemExit(f"Arquivo de prompts não encontrado: {args.prompts}")
      prompts_custom = {int(k): v for k, v in json.loads(args.prompts.read_text(encoding="utf-8")).items()}
  ```
  As novas flags de referência devem seguir exatamente esse estilo
  (`type=Path`, validação com `SystemExit`, chaves `int(k)` 1-based).
- Merge do manifesto de imagens (`main()`, já existe): mescla por chave
  `"frase"`, preservando entradas não regeneradas. As novas chaves
  (`"referencia"`, `"referencia_denoise"`) só entram no dict de resultado
  quando aquela frase usou o branch i2i — sem quebrar o merge existente.

**Novas flags** (família com prefixo comum, todas opcionais):

- `--referencia <arquivo>.json`: `{"<frase>": "<caminho da imagem de
  referência>"}`, mesma convenção 1-based de `--prompts` (chaves são
  string no JSON, convertidas pra `int` no parse, igual ao padrão acima).
- `--referencia-denoise <float>` (default inicial `0.5` — **o valor final
  deve ser decidido pelo sweep de verificação abaixo, não travado sem
  comparar**).
- `--referencia-workflow <path>` (default
  `comfy/image_zimage_turbo_i2i.json`) — só é lido do disco quando
  `args.referencia` foi passado.

**Validação antecipada em `main()`** (antes de qualquer chamada de rede,
mesmo padrão de "falhar cedo" já usado pra `--manifesto`/`--workflow`):
- Cada caminho de imagem dentro do JSON de `--referencia` precisa
  existir no disco — `SystemExit` citando frase + caminho na primeira
  falha.
- Aviso (`print`, **não** `SystemExit`) se alguma chave de `--referencia`
  não corresponder a nenhuma frase das `tarefas` desta execução — comparar
  `set(referencias.keys())` contra `{j for j, _ in tarefas}` e avisar as
  sobras. Não travar o script — mantém o tom permissivo do resto do
  arquivo (frase sem entrada em `--prompts` também não é erro, por
  exemplo).

**Upload da imagem de referência**: nova função, ex.
`enviar_imagem_referencia(server: str, caminho: Path) -> str` (retorna o
identificador pronto pra `LoadImage.inputs.image`, no formato
`"subpasta/nome"` se houver subpasta, senão só `"nome"`). Implementação
sugerida — **não** copiar a construção manual de multipart/`urllib` de
`video_gen/gerar_video.py:56-81` (existe nesse projeto irmão, mas
`gerar_imagens.py` já importa `requests`, que faz isso de forma mais
simples):

```python
import mimetypes

def enviar_imagem_referencia(server: str, caminho: Path) -> str:
    mimetype = mimetypes.guess_type(caminho.name)[0] or "application/octet-stream"
    resp = requests.post(
        f"{server}/upload/image",
        files={"image": (caminho.name, caminho.read_bytes(), mimetype)},
        timeout=60,
    )
    resp.raise_for_status()
    info = resp.json()
    subfolder = info.get("subfolder", "")
    return f"{subfolder}/{info['name']}" if subfolder else info["name"]
```

Use sempre o `name`/`subfolder` **da resposta**, não assuma que é igual
ao nome do arquivo local — o próprio `/upload/image` do ComfyUI já faz
dedup por hash e resolve colisão de nome (renomeia com sufixo se o
conteúdo for diferente). Como vários projetos desta plataforma usam o
mesmo nome-base (`texto_FF.png`), colisão entre projetos diferentes VAI
acontecer — o servidor já cobre isso, só não assuma que o nome enviado é
o nome final.

**Cache de upload dentro de `main()`**: um dict simples
`{caminho_local: nome_upload}` (escopo local da função, não global) pra
não reenviar a mesma imagem quando várias frases apontam pro mesmo
arquivo — que é justamente o fluxo principal de uso desta feature (várias
frases do mesmo personagem, mesma imagem de referência).

**No branch i2i de `gerar_imagem()`** (ou equivalente): além de
`LoadImage.inputs.image` e `KSampler.denoise`, **também setar
`aspect_ratio` no node `7`** (`_ZIMAGE_NODE_RESOLUCAO`) — o `ImageScale`
novo depende desse node via link pra `width`/`height`; é fácil esquecer
essa linha por não ser um dos 3 nodes novos, mas sem ela o
redimensionamento da referência usa o aspect ratio salvo no JSON, não o
`--aspect-ratio` pedido na chamada.

**Manifesto** (`<nome>_imagens_manifesto.json`): adicionar campos
opcionais `"referencia"` (caminho local usado, string) e
`"referencia_denoise"` (float) só nas entradas que passaram pelo branch
i2i — mesma filosofia de rastreabilidade que já vale pra `prompt_final`/
`arquivo_comfy` (CLAUDE.md é explícito: preservar esses campos em
qualquer refactor é o único jeito de saber depois qual prompt/config
gerou qual imagem).

### 3. Fluxo de uso recomendado (documentar em `CLAUDE.md` depois de implementar)

Gerar as imagens normalmente primeiro (sem `--referencia`). Escolher
visualmente a melhor imagem já gerada do personagem como referência —
**priorizando uma cena de pose/enquadramento parecido com a(s) frase(s)
que vão reutilizá-la**, não só "a imagem mais bonita do personagem":
denoise parcial preserva estrutura espacial da referência (pose,
posição de elementos), não só "quem é a pessoa". Referenciar uma pose
muito diferente da cena-alvo tende a gerar uma composição híbrida forçada
em vez de honrar a cena nova (risco real — a Fase 5 da verificação testa
isso de propósito). Depois, regenerar só as frases daquele personagem:
`--frases X,Y,Z --referencia arquivo.json`. Não precisa de uma etapa
dedicada de "gerar imagem de referência" — reaproveita uma imagem que já
seria gerada de qualquer forma.

### 4. Fora de escopo (não construir agora)

Ver "Rota alternativa mais robusta, descartada por ora" acima (LoRA via
`Comfyui-ZiT-Lora-loader` + treino externo). Só documentar como opção
futura se este mecanismo se mostrar insuficiente.

## Arquivos principais a tocar

- `scripts/gerar_imagens.py` — flags novas, `enviar_imagem_referencia()`,
  3º branch em `gerar_imagem()`, mudanças em `main()` (carregar 2º
  workflow condicionalmente, escolher por frase, cache de upload,
  validação antecipada, campos novos no manifesto).
- `comfy/image_zimage_turbo_i2i.json` (novo arquivo) — grafo detalhado
  acima.
- `CLAUDE.md` (deste subprojeto) — nova subseção documentando o mecanismo
  (na seção de `scripts/gerar_imagens.py`), no mesmo estilo do resto do
  arquivo (rationale + gotchas testados, não só "como usar"). Atualizar
  também a lista de arquivos em `comfy/` se relevante.
- `comfy/GOTCHAS.md` — se a verificação abaixo revelar algum
  comportamento não-óbvio (ex. faixa de denoise onde a identidade se
  perde, artefato de ghosting em determinada combinação), registrar lá,
  no mesmo formato numerado dos itens existentes (sintoma → causa →
  o que não funcionou → o que funcionou).

## Plano de verificação (rodar de verdade, não só ler o código)

Usar o ComfyUI local já rodando e `Projetos/Video_9/` (frase 7 → frase 8,
caso real já documentado em `analise.md`) como banco de teste. **Não
sobrescrever o vídeo já entregue/commitado** — gerar resultados de teste
em arquivos separados (ex. copiar `texto_08.png` pra
`texto_08_baseline_manual.png` antes de mexer); só adotar de volta em
`Video_9` (sobrescrever `texto_08.png`/manifesto/remontar o vídeo) se o
resultado for visivelmente melhor que o fix manual já aplicado, **e com
aprovação explícita de quem estiver rodando esta sessão** antes de
sobrescrever.

1. **Sanity do ambiente**: `GET http://127.0.0.1:8188/system_stats`
   confirma o ComfyUI de pé e sem job travado. Rodar uma geração t2i comum
   do `gerar_imagens.py` já existente (sem nenhuma mudança de código,
   fluxo de hoje) como controle de que o ambiente está saudável antes de
   integrar qualquer coisa nova.
2. **Grafo isolado**: montar `comfy/image_zimage_turbo_i2i.json` conforme
   o design acima. Upload manual de
   `Projetos/Video_9/imagens/texto_07.png` via `POST /upload/image`
   (pode ser com `curl`, Python solto, ou o que for mais rápido — não
   precisa passar pelo script ainda), pegar o nome retornado, montar o
   JSON do grafo à mão preenchendo `LoadImage.image`, o prompt da frase 8
   (`"O órgão se regenerava durante a noite, só pra ser comido de novo na
   manhã seguinte."` + `_SUFIXO_SEGURANCA`), `denoise=0.5`. `POST
   /prompt` direto, confirmar resposta sem `node_errors`, `GET
   /history/{id}` até completar, baixar via `/view`. Critério de sucesso:
   imagem plausível, sem erro de node — isola "o grafo funciona" de "o
   script está certo", antes de integrar em Python.
3. **Integração + sweep de denoise**: implementar as mudanças em
   `scripts/gerar_imagens.py`. Criar
   `Projetos/Video_9/texto_referencia.json` = `{"8":
   "Projetos/Video_9/imagens/texto_07.png"}`. Rodar:
   ```
   .\venv\Scripts\python.exe scripts\gerar_imagens.py Projetos\Video_9\texto_manifesto.json --frases 8 --referencia Projetos\Video_9\texto_referencia.json --referencia-denoise 0.35
   ```
   Repetir com `0.5` e `0.65`, fazendo backup do PNG resultante entre
   cada rodada (o script sempre grava em `texto_08.png`, sobrescrevendo).
   Comparar lado a lado com `texto_08_baseline_manual.png` (fix manual já
   commitado): fidelidade de identidade (cabelo loiro, capa verde-escura
   aberta, ferimento brilhando no torso), fidelidade à cena PRÓPRIA da
   frase 8 (não uma cópia da pose de pé/acorrentado-olhando-a-águia da
   frase 7 — a frase 8 é sobre regeneração noturna, sem a águia em cena),
   ausência de ghosting/dupla exposição. Esse sweep decide o valor final
   de default pra `--referencia-denoise` no código — não travar em `0.5`
   sem comparar os 3 resultados.
4. **Regressão do caminho padrão**: rodar `--frases 1` (frase sem entrada
   em `--referencia`) e confirmar que o comportamento é idêntico ao de
   antes da mudança — inclusive checando que `workflow_i2i` nem é
   carregado quando `--referencia` não é passado. Testar `--referencia`
   apontando pra um caminho inexistente → `SystemExit` imediato, zero
   chamadas de rede. Testar `--referencia` com uma chave fora do range de
   frases desta run (ex. `"99"`) → aviso impresso, script continua e
   termina normalmente.
5. **Caso desfavorável de propósito**: criar um segundo arquivo de
   referência apontando a frase 6 (`"Zeus não perdoou."`, cena de trono/
   tempestade — personagem diferente, Zeus não Prometeu) pra
   `Projetos/Video_9/imagens/texto_02.png` (Prometeu fugindo com a
   tocha, pose bem diferente de "sentado num trono"). Gerar e confirmar
   que sai visivelmente ruim/híbrido — isso é esperado e vira orientação
   de uso ("escolha referência com pose/cena compatível", ver seção 3),
   não um bug a corrigir.
6. **Escala**: regenerar um grupo numa única chamada (ex. `--frases
   6,7,8,9`, todas no mesmo arquivo de referência apontando pra
   `texto_07.png` — ignore que a frase 6 é tematicamente Zeus, é só teste
   de mecanismo de cache/escala) e confirmar, via log ou instrumentação
   temporária, que o cache de upload evita reenviar a mesma imagem 4
   vezes.

Depois de tudo validado: atualizar `CLAUDE.md` e (se aplicável)
`comfy/GOTCHAS.md`, e seguir o fluxo Git obrigatório do repositório
(commit descritivo cobrindo só os arquivos desta feature + push).
