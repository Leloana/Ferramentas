---
name: buscar-trending-topics
description: |
  Busca assuntos em alta no Google Trends Brasil (via WebSearch) e propõe uma lista de ideias de
  conteúdo pra vídeo curto da tts_platform_pt a partir deles — sem filtro de nicho fixo, qualquer
  assunto em alta entra na lista, cada um já com um ângulo sugerido. Você escolhe qual(is) seguir. Use
  quando o usuário invocar `/buscar-trending-topics` ou pedir em linguagem natural por ideias de vídeo
  baseadas em trending topics, assuntos em alta, o que está bombando agora, ou pedir sugestão de tema
  pro próximo vídeo sem já ter um em mente. Não escreve texto.md nem descricao.md — é só
  descoberta+curadoria; depois de escolher um tema, use a skill gerar-texto pra produzir o roteiro.
---

# Buscar Trending Topics — Ideias de Conteúdo

Esta skill só pesquisa e propõe. Ela **não** escreve `texto.md`/`descricao.md` nem cria pastas em
`Projetos/ideias/` — isso é trabalho da skill [gerar-texto](../gerar-texto/SKILL.md), que deve ser
invocada depois que o usuário escolher um tema aqui.

## 1. Buscar os trending topics

- A ferramenta `WebSearch` é deferred — carregue com `ToolSearch` (`select:WebSearch`) antes de tentar
  usá-la.
- Não existe API dedicada de Google Trends disponível aqui — a busca é feita via `WebSearch` normal.
  Rode **várias queries diferentes** (não uma só) pra cruzar resultado, já que uma query isolada pode
  cair numa página cacheada/desatualizada:
  - `google trends brasil hoje assuntos mais buscados`
  - `trends.google.com.br trending now brasil`
  - `o que está bombando no google brasil <data de hoje>`
  - Vale complementar com `mais buscados no youtube brasil hoje` se os resultados de busca vierem
    fracos — o objetivo é chegar numa lista de pelo menos ~15-20 tópicos brutos antes de filtrar.
- Use a data atual (contexto da conversa) pra julgar se um resultado é de fato recente ou é uma página
  antiga que o buscador só indexou de novo.

## 2. Triagem inicial — não é filtro de nicho, é filtro de viabilidade

O usuário decidiu explicitamente **não restringir por nicho** (não precisa ser história/curiosidades
como os vídeos já feitos) — qualquer assunto em alta pode entrar na lista. Mesmo assim, descarte antes
de montar a pitch:

- **Tópicos puramente efêmeros sem ângulo durável**: placar de jogo de ontem, resultado que já
  desatualizou, algo que só faz sentido nas próximas horas. Se não existe um recorte que ainda faça
  sentido em uma semana, descarte (ou vire fato/curiosidade por trás do evento, não o evento em si).
- **Tópicos sensíveis/arriscados**: tragédias, acusações não confirmadas, qualquer coisa que vire
  conteúdo sensacionalista sobre pessoa privada ou situação de sofrimento real. Não vale o engajamento.
- **Nomes ambíguos sem história clara por trás** (ex.: um nome próprio isolado sem contexto do porquê
  está em alta) — sem uma pesquisa rápida que destrave um ângulo, descarte em vez de forçar.

Tudo o que sobrar continua elegível, independente de já ter relação com os temas anteriores do canal.

## 3. Montar uma pitch curta por tópico viável

Pra cada tópico que passou da triagem, escreva:

```
<Tópico> — <por que está em alta, 1 frase curta>
  Ângulo sugerido: <recorte concreto de vídeo, não o assunto genérico>
  Formato: <vídeo avulso | série de N partes> — <1 frase justificando se for série>
```

- O "ângulo sugerido" precisa ser específico o bastante pra alimentar o passo 2 da skill
  [gerar-texto](../gerar-texto/SKILL.md) sem precisar de mais uma rodada de pergunta — mesmo critério
  de lá: um recorte, não um assunto amplo ("a corrida espacial entre EUA e URSS pelos bastidores
  técnicos", não só "espaço").
- Não invente fatos pra sustentar o ângulo — se a busca não trouxe detalhe suficiente pra um ângulo
  seguro, rode mais uma busca específica daquele tópico antes de descartar ou de forçar uma pitch rasa.

## 4. Apresentar a lista e deixar o usuário escolher

- Liste tudo em markdown corrido (não use `AskUserQuestion` aqui — a lista costuma passar de 4 itens,
  que é o teto da ferramenta). Agrupar informalmente por "mais forte"/"mais arriscado" se ajudar a
  leitura, mas sem exagerar em categorização.
- Deixe claro que trending topics são perecíveis: se o usuário não decidir na hora, os itens podem
  perder relevância em poucos dias — oferecer rodar a skill de novo mais perto da hora de produzir é
  melhor do que confiar numa lista velha.
- Pergunte qual(is) tópico(s) o usuário quer seguir (pode ser mais de um, cada um vira um projeto
  independente).

## 5. Depois de escolher

Esta skill termina aqui — nenhum arquivo é criado. Para cada tópico escolhido, oriente (ou já
encaminhe, se o usuário confirmar) pra skill `gerar-texto` com o tema+ângulo já definidos, ex.:
`/gerar-texto "<ângulo escolhido>" <N partes>`.
