# Análise: Z-Image-Turbo vs Krea2-Turbo (geração de imagens)

Comparação entre o modelo de geração de imagem novo (`Z-Image-Turbo`,
workflow `comfy/image_zimage_turbo_t2i.json`) e o antigo (`krea2_turbo`,
workflow `comfy/image_krea2_turbo_t2i.json`), feita a partir da produção do
vídeo `Projetos/Video_9/` (mito de Prometeu, 17 imagens, uma por frase).

**Metodologia e limitação**: não foi um teste A/B com os mesmos prompts nos
dois modelos — foi uma rodada nova de 17 gerações no Z-Image, comparada ao
histórico de defeitos já catalogado do Krea2 em
[comfy/GOTCHAS.md](comfy/GOTCHAS.md) (acumulado ao longo dos projetos
`Video_1` a `Video_8`). Amostra pequena (1 projeto, 17 imagens); tratar como
indicativo, não como número estatisticamente robusto.

## Resumo

Nesta rodada o Z-Image-Turbo **não reproduziu nenhum** dos defeitos mais
frequentes/graves já catalogados do Krea2 (nudez indevida, texto borrado
desenhado na cena, rotação 90°/tríptico em 9:16, desvio para estilo anime
fora do tema) em 17 gerações. Em compensação, produziu **um problema novo e
mais grave em termos de risco de conteúdo**, que não tem precedente
catalogado no Krea2: uma cena com várias pessoas em contexto vulnerável
saiu com roupas insuficientes e aparência potencialmente menor de idade.
Isso não significa que o Z-Image "alucina menos" no sentido amplo — significa
que a natureza da alucinação mudou, e o novo tipo é mais sério.

## Achados desta rodada (Z-Image-Turbo)

### 1. CRÍTICO — pessoas com roupa insuficiente e aparência potencialmente menor de idade

Frase 4 (`"Antes disso, os humanos não tinham calor, ferramentas, nem nada
que os diferenciasse dos outros animais."`), prompt enviado: *"primitive
early humans huddled together in a dark cold cave, moonlight only, no fire,
desperate expressions, wide cinematic shot"* (+ o guarda-corpo padrão
`_SUFIXO_SEGURANCA` do script, aplicado automaticamente).

Resultado (`texto_04.png`, geração original, não incluída no vídeo final):
um grupo de ~11 pessoas agachadas numa caverna, várias com aparência jovem
e roupas mínimas/esfarrapadas expondo bastante pele, em pose de medo —
combinação que li como preocupante o suficiente pra não usar no vídeo.

**Diferença em relação ao guarda-corpo de nudez do Krea2** (item 1 do
GOTCHAS.md): lá o problema era nudez adulta explícita, resolvido declarando
vestimenta no prompt. Aqui o `_SUFIXO_SEGURANCA` (`", fully clothed,
appropriate attire, no nudity"`) **já estava presente** e não foi
suficiente — o problema não era ausência de menção a roupa, era a
combinação specific de "grupo humano primitivo" + "desespero" que o modelo
associou a pouca cobertura e traços jovens, mesmo com "fully clothed" no
prompt.

**Correção aplicada (1ª rodada)**: reescrevi o prompt sendo explícito sobre
idade e cobertura — *"a small group of **adult** Stone Age men and women,
**wrapped head to toe in thick heavy fur cloaks covering their entire
bodies**, huddled together for warmth in a dark cold cave, moonlight only,
no fire, worried **adult** faces, wide cinematic shot"*. Resolveu o
problema de segurança (rostos claramente adultos, corpo inteiro coberto),
mas o ambiente saiu ambíguo — mais um alto rochoso pouco legível como
caverna do que um interior de caverna de fato (revisão humana apontou
isso).

**Correção aplicada (2ª rodada)**: reforcei o ambiente no início do prompt
em vez de deixá-lo como detalhe secundário — *"wide shot **deep inside a
dark damp stone cave** at night, **rocky cave walls and ceiling
surrounding the scene**, ... huddled together for warmth **near the cave
entrance**, faint moonlight coming through **the cave opening** in the
background, ..."*. Regenerado (`--frases 4`), agora com teto/paredes
rochosas visíveis e a abertura da caverna com a lua ao fundo — lê como
caverna sem ambiguidade. Essa é a versão usada no vídeo final.

**Lição**: mencionar o ambiente uma vez não bastou — ele precisou virar o
sujeito da primeira cláusula do prompt (não só um detalhe no meio da
frase) pra o modelo priorizar renderizá-lo de forma legível.

**Recomendação pro projeto**: ao escrever `texto_prompts.json` pra cenas
com múltiplos humanos em contexto de vulnerabilidade/desespero/frio, ser
explícito com "adult"/"adulto" e descrever a cobertura de roupa em detalhe
(não só "fully clothed" genérico) — pelo menos até esse comportamento ser
melhor entendido. Continua valendo (com mais razão ainda) a regra já
existente de revisar visualmente cada imagem antes de rodar
`montar_video.py`.

### 2. Moderado — deriva de identidade/estilo entre imagens da mesma "personagem" (corrigido)

Frase 8 (Prometeu acorrentado, cena de continuidade da frase 7): o prompt
pedia uma figura acorrentada num penhasco à luz da lua, sem descrever a
aparência física. Na frase 7 saiu um homem loiro em trajes gregos (coerente
com a frase 2); na frase 8, a "mesma" cena saiu como uma mulher em trajes
de estilo asiático (tipo hanfu/wuxia), sem relação com o titã grego
estabelecido nas imagens anteriores.

Não é bem uma alucinação de conteúdo impróprio, é falta de continuidade de
personagem — nem o workflow do Z-Image nem o do Krea2 têm mecanismo de
referência de personagem entre gerações (cada frase é uma chamada
independente ao sampler, sem imagem-base), então isso é esperado dos dois
modelos igualmente; não é uma regressão do Z-Image.

**Correção aplicada**: reescrevi o prompt repetindo os traços físicos já
estabelecidos na frase 7 — *"**a young man with long blond hair and an open
dark green cloak exposing his bare chest**, chained by the ankle to a rocky
mountain cliff, alone at night under moonlight, a faint warm glow over his
bare torso where a wound is healing, ..."* — em vez de descrever só a pose
("a chained figure...") e deixar o modelo reinventar quem é essa figura.
Regenerado (`--frases 8`), saiu visualmente consistente com a frase 7
(mesmo cabelo loiro, mesma capa verde-escura aberta). Essa é a versão usada
no vídeo final.

Esse fix manual (repetir descritores físicos no prompt) resolve o caso
pontual, mas não escala bem pra roteiros com um personagem recorrente em
muitas frases, nem garante identidade pixel-a-pixel. Ficou combinado com o
usuário planejar, à parte deste documento, um mecanismo mais robusto de
continuidade de personagem (ex.: IPAdapter/InstantID no ComfyUI) — como
melhoria opcional pra projetos futuros que dependam disso, já que a maioria
dos vídeos desta plataforma não tem um personagem único recorrente.

### 3. Leve — inversão de escala/composição

Frase 9 (`texto_09.png`): pedi um deus pequeno ao longe olhando um titã
acorrentado; saiu invertido (a figura acorrentada em primeiro plano/grande,
a "testemunha" pequena ao fundo). Sem prejuízo visual pro vídeo — só uma
interpretação diferente da composição pedida. Mantida.

### Sem ocorrência (categorias que o Krea2 tinha catalogadas)

Nas 17 imagens desta rodada, **zero ocorrências** de:

- Texto borrado desenhado sobre a cena (item 2 do GOTCHAS.md do Krea2).
- Rotação 90° ou tríptico em formato 9:16 (item 3).
- Desvio completo do prompt pra estilo anime/fora de tema (item 8 — esse
  foi justamente o motivo documentado no código
  (`scripts/gerar_imagens.py`, comentário sobre `_ZIMAGE_NODE_PROMPT`) pra
  ter trocado de modelo).
- Prompt bilíngue engasgando o refino (item 7) — **não aplicável**: o
  workflow do Z-Image não tem etapa de refino via LLM (`TextGenerate`), o
  texto do `--prompts` vai direto pro `CLIPTextEncode`. Isso elimina de
  raiz a classe inteira de bugs que vinham do refino (itens 2 e 7 do
  GOTCHAS.md), mas também significa que não há expansão automática de
  prompt — a qualidade da imagem depende inteiramente do que for escrito à
  mão em `texto_prompts.json`, sem uma segunda passada de "polimento".

## Diferenças operacionais (não relacionadas a alucinação)

- `scripts/gerar_imagens.py` já suporta os dois workflows: detecta qual é
  qual pela presença do node `30:24` (`_NODE_REFINAR`, exclusivo do Krea2)
  no JSON carregado — não precisa de flag extra além de `--workflow
  comfy/image_zimage_turbo_t2i.json`.
- Sem etapa de refino, o Z-Image não aplica `_REGRA_SEM_TEXTO` nem
  `_REGRA_PROMPT_CURTO` (são injetadas só no system prompt do
  `TextGenerate` do Krea2) — essas regras seguem existindo no código só
  pro caminho do Krea2.
- Tempo de geração não foi medido com rigor nesta rodada (não há timestamp
  por imagem no log); qualitativamente, as 17 gerações completaram num
  único lote sem timeout e sem nenhum caso parecido com o outlier de 362s
  documentado pro Krea2 (item 6 do GOTCHAS.md), mas isso não foi validado
  com múltiplas repetições do mesmo prompt como seria necessário pra uma
  comparação de timing confiável.

## Conclusão

Pra esta amostra, o Z-Image-Turbo é uma melhora clara nas categorias de
defeito que motivaram a troca (desvio de tema/anime, texto borrado,
formato 9:16 instável) — zero ocorrências dessas em 17 imagens, contra uma
taxa não-trivial documentada pro Krea2 (ex.: 3 de 11 imagens com desvio pra
anime numa leva). Mas não é estritamente "menos alucinação" em todas as
dimensões: produziu uma falha de segurança de conteúdo (item 1 acima) mais
séria do que qualquer coisa catalogada pro Krea2, mesmo com o mesmo
guarda-corpo de segurança aplicado. A recomendação prática não muda desde o
GOTCHAS.md original — **"rodou sem erro" nunca foi sinal de "saiu certo"**
— só fica mais importante prestar atenção específica em cenas com múltiplas
pessoas em contexto vulnerável.
