---
name: gerar-texto
description: |
  Gera roteiro(s) de narração (texto.md) e legenda/hashtags (descricao.md) para um novo vídeo curto
  ou série de vídeos da tts_platform_pt, no mesmo estilo e formato da série "História da Humanidade"
  (Projetos/Video_1/historia_humanidade*). Use quando o usuário invocar `/gerar-texto <tema> <partes>`
  (ex.: "/gerar-texto dinossauros 4") ou pedir em linguagem natural pra criar/gerar textos, roteiro(s)
  ou um novo projeto de vídeo sobre um tema. Cria rascunhos em Projetos/ideias/<nome>/ com texto.md,
  descricao.md e vozes.md por parte — prontos pra revisar e, quando aprovados, promover pra
  Projetos/Video_N/<nome>[_parteN]/ e alimentar scripts/gerar_video.py.
---

# Gerar Texto — Roteiros para Vídeos Curtos

Esta skill só escreve arquivos de texto (roteiro + legenda). Ela **não** chama o servidor TTS, o
ComfyUI, nem nenhum script de `scripts/` — a síntese de áudio/vídeo fica pra um passo manual depois.
Para o pipeline completo (áudio, imagens, montagem), ver
[CLAUDE.md](../../../CLAUDE.md) deste subprojeto.

## 1. Interpretar os argumentos

- Formato esperado: `/gerar-texto <tema> <número de partes>` — o último token dos args que for um
  número inteiro é N (partes); o resto é o `<tema>`.
- Sem número de partes: pergunte quantas partes antes de escrever qualquer coisa.
- N alto (mais de ~8): confirme com o usuário antes de gerar tudo — é bastante texto/vídeo pra revisar
  de uma vez.
- Confira `Projetos/ideias/` e `Projetos/Video_*/` antes de escrever: se já existir uma pasta com o
  slug que você pretende usar (passo 5), avise o usuário em vez de sobrescrever.

## 2. Avaliar se o tema já tem um recorte claro

Um tema está específico o suficiente quando já implica um **ângulo** — um recorte de conteúdo, não só
um assunto amplo. "A extinção dos dinossauros por impacto de asteroide" tem ângulo. "Dinossauros"
sozinho não tem: dá pra virar curiosidades soltas, panorama descritivo das espécies, hábitos e
comportamento, a extinção, a evolução ao longo do tempo — cada recorte vira uma série bem diferente.

**Se o tema for amplo demais, pergunte antes de escrever** (via AskUserQuestion). Monte de 3 a 4
opções pensadas para ESSE tema específico — não uma lista genérica fixa —, cobrindo dimensões como:

- Curiosidades soltas vs. panorama descritivo vs. um evento/período específico vs. um aspecto
  particular (comportamento, biologia, cultura, impacto, etc.).
- Quando fizer sentido pro tema: a série deve ser narrativa contínua (como "História da Humanidade",
  onde a parte 2 emenda direto na parte 1, sem recapitular) ou uma coletânea de partes independentes
  (cada parte fecha sozinha, tipo episódios temáticos)?

Não pergunte se o pedido do usuário já deixa isso implícito (ex.: "curiosidades sobre polvos", "como
os vikings navegavam sem bússola" já têm ângulo definido — vá direto pro passo 3).

## 3. Planejar o arco das N partes

Antes de escrever o texto final de cada parte, decida (mentalmente ou em rascunho curto, não precisa
mostrar ao usuário) o sub-tema/foco de cada uma das N partes, na ordem que fará elas se encaixarem.

- **Série narrativa/cronológica**: cada parte emenda na anterior sem recapitular — a referência nunca
  reexplica o que já foi dito (a parte 2 de "História da Humanidade" começa em "As populações
  explodiram.", direto na consequência do fim da parte 1). É pensada pra assistir em ordem.
- **Coletânea temática** (ex.: curiosidades): cada parte agrupa um subconjunto coerente de
  fatos/aspectos daquele tema, e faz sentido sozinha, sem depender das outras partes.

## 4. Escrever cada `texto.md`

Regras de estilo extraídas da série de referência (`Projetos/Video_1/historia_humanidade*/texto.md`):

- **~130-150 palavras por parte** (faixa medida nos 5 textos existentes: 106-155, média ~135) — é o
  que rende ~1 minuto de fala no XTTS-v2. Conte as palavras antes de fechar cada parte e ajuste.
- **Texto puro da narração**: só o parágrafo corrido, sem título markdown, sem numeração, sem marcação
  de frase — `gerar_video.py` sintetiza o arquivo exatamente como está (a divisão em frases pro TTS é
  automática, via pontuação).
- **Gancho forte na primeira frase** — é o que prende alguém nos primeiros 2-3 segundos de vídeo. Evite
  abrir com preâmbulo/contexto.
- **Frases médias, tom documentário/expositivo, português claro** — sujeito+ação, sem empilhar muitas
  orações subordinadas. Releia em voz alta pra sentir a cadência.
- **Evite duas datas completas ("dia de mês de ano") na mesma frase** — bug conhecido do XTTS-v2 em
  português faz o modelo alucinar/repetir nesse caso, e a frase sai bem mais longa que o esperado (ver
  Gotchas do [CLAUDE.md](../../../CLAUDE.md)). Se o tema envolver nascimento/morte ou início/fim com
  datas, separe em duas frases.
- Reticências (`...`) e travessão aparecem no texto de referência pra marcar pausa dramática — pode
  usar com moderação, não é obrigatório.

## 5. Criar a estrutura de pastas — sempre dentro de `Projetos/ideias/`

Texto gerado por esta skill é **rascunho**, não produção: não crie diretamente
`Projetos/Video_N/<nome>[_parteN]/` (essa convenção, documentada no
[CLAUDE.md](../../../CLAUDE.md), é pra projetos já em produção — com `audio/`, `imagens/`, `video/`
associados). Em vez disso, tudo entra em `Projetos/ideias/<slug>/`:

- Gere um slug do tema+ângulo (minúsculo, sem acento, `_` no lugar de espaço).
- **N = 1** (vídeo avulso): os arquivos vão direto em `Projetos/ideias/<slug>/`.
- **N > 1** (série): uma subpasta por parte, `Projetos/ideias/<slug>/parte1/`,
  `Projetos/ideias/<slug>/parte2/`, ... — os nomes espelham exatamente o que cada parte vai virar
  depois de promovida (ver passo 7), só que agrupadas dentro de uma pasta só pra facilitar review.
- Se N = 1, não inclua indicador de parte no `descricao.md`.

Em cada pasta (ou subpasta de parte), crie três arquivos:

**`texto.md`** — o parágrafo daquela parte (passo 4), e mais nada.

**`descricao.md`** — legenda pronta pra colar, texto puro (sem cabeçalho markdown), neste formato:

```
<Título da série> — Parte X/N 👇

<gancho de 1-2 frases terminando em emoji temático>

<parágrafo resumindo o que essa parte cobre>

<hashtags>
```

- Primeira linha omitida se N=1 (vídeo avulso); na última parte da série vira "Parte N/N (final)".
- Título da série: curto (2-5 palavras), reflete o tema+ângulo escolhido — não precisa repetir o slug
  da pasta literalmente.
- Hashtags: defina um **bloco-base fixo pra série inteira**, adaptado ao tema (não copie o de "história
  da humanidade" literalmente — ele é específico daquela série), e repita esse mesmo bloco em TODAS as
  partes, mais 3-5 hashtags específicas de cada parte. É o bloco-base repetido que faz a série ficar
  linkada nas buscas por hashtag — não varie entre partes.

**`vozes.md`** — sempre com o par padrão da plataforma:

```
Mulher: Ana Florence
Homem: Dionisio Schuyler
```

## 6. Depois de gerar

Resuma pro usuário o que foi criado (pasta em `Projetos/ideias/` + contagem de palavras de cada
`texto.md`) e deixe claro que ainda é rascunho — nada foi promovido a projeto de produção.

## 7. Promover uma ideia pra produção

Só quando o usuário confirmar que quer seguir com aquela ideia (não automaticamente após gerar):

- Cada **produção** (a ideia inteira, não cada parte) ganha uma pasta numerada
  `Projetos/Video_N/` — `Video_1` foi a primeira produção feita
  (`historia_humanidade`, 5 partes), o número é sequencial por produção, não
  por parte. Determine N: liste `Projetos/Video_*/` e use o próximo inteiro
  livre — a menos que o usuário já tenha reservado/criado uma pasta
  `Video_N` vazia pra essa ideia especificamente (confirme com ele se não
  tiver certeza de qual N usar).
- Mova cada `Projetos/ideias/<slug>/parteN/` pro destino real da convenção —
  `Projetos/Video_N/<slug>/` pra parte 1, `Projetos/Video_N/<slug>_parte2/`
  pra parte 2, e assim por diante (pra N = 1 parte sem subpastas, mova
  `Projetos/ideias/<slug>/` inteira pra `Projetos/Video_N/<slug>/`). Confira
  antes que não exista já uma pasta com esse nome dentro desse `Video_N/`
  pra não sobrescrever produção existente.
- Depois de mover, oriente os próximos passos manuais fora do escopo desta skill:
  - Revisar os textos de novo, principalmente frases com números/datas (regra do passo 4).
  - Rodar `scripts/gerar_video.py` em cada pasta promovida pra sintetizar o áudio (servidor precisa
    estar rodando).
  - Se for gerar vídeo com imagens, escrever `texto_prompts.json` à mão (ver convenção no CLAUDE.md)
    antes de `scripts/gerar_imagens.py` — não é gerado por esta skill.
  - Depois de `scripts/montar_video.py`, **todo vídeo termina com
    `scripts/gerar_capa.py`** — gera a imagem de capa/thumbnail (título real
    desenhado por cima de uma das imagens de fundo já geradas, não pedido ao
    modelo de difusão). Sem `--titulo`, usa a 1ª linha do `descricao.md` que
    esta skill já escreveu no passo 5. É o último passo do pipeline: sem
    capa, o vídeo não está pronto pra postar.
