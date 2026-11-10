# Próxima etapa — qualidade musical, criação e experiência de uso

Preparado em 2026-11-10. Este documento descreve trabalho futuro; as propostas
abaixo ainda precisam ser investigadas, implementadas e avaliadas.

## 1. Objetivo geral

Transformar o Partitura em uma ferramenta que entregue um arranjo de piano coerente,
natural e adequado à dificuldade escolhida, com pouca configuração pelo usuário.
Além de transcrever, permitir criar introduções e enriquecer acompanhamentos de
forma controlada. Melhorar a leitura sincronizada e preparar letras em japonês.

A experiência desejada é: escolher uma música, escolher a dificuldade e gerar.
A seleção de modelos, estilos e regras deve ser responsabilidade do sistema,
fundamentada em testes. Recursos criativos podem ficar em uma área de personalização.

Continuar com processamento local e sem depender de LLM. Novos modelos e
dependências devem ser avaliados quanto a qualidade, tempo, memória e compatibilidade
com o ambiente atual, incluindo Windows e GPU de 12 GB.

## 2. Ponto de partida

- O projeto gera PDF, MusicXML, MIDI e prévia de piano.
- Há oito músicas e 120 partituras na biblioteca local, com cinco versões e três níveis.
- Principais atuais: Acordes no Fácil e Híbrido AMT no Médio/Difícil.
- Os arranjos foram revisados para reduzir aberturas e saltos. Isso melhora o alcance,
  mas não garante harmonia correta, ritmo natural ou fidelidade à gravação.
- A prévia e o visualizador compartilham os tempos do MusicXML. A barra já atravessa
  pausas continuamente; a gravação original ainda não está sincronizada.
- Existe proteção de ataques/deslizamentos da voz antes da quantização. Foi validada
  em Para Machucar Meu Coração e está ativa nas novas gerações de Acordes/Híbridos.
- Os outros arquivos antigos ainda precisam ser regenerados para receber essa proteção.
- Os números de concordância melódica usam a extração vocal do próprio pipeline.
  Não equivalem a acurácia contra uma partitura humana.

Referências internas:

- [Handoff](HANDOFF.md), especialmente as seções mais recentes.
- [Análise das partituras](ANALISE_PARTITURAS.md).
- [Diagnóstico dos três trechos](DIAGNOSTICO_CORACAO.md).
- [Exemplos de antes/depois](exemplos/README.md).

## 3. Frente 1 — investigar harmonia e naturalidade

### Pergunta principal

Por que um arranjo pode ser tocável e ainda soar estranho? Separar erros de
transcrição, escolhas harmônicas e problemas de ritmo/execução antes de corrigi-los.

### Investigações

1. **Notas da melodia:** distinguir altura estável, portamento, vibrato, ataque
   crepitante, erro de oitava e vazamento de instrumento na voz isolada.
2. **Acordes detectados:** verificar fundamental, qualidade, inversão, baixo e
   fronteiras de mudança. Identificar trocas rápidas que não representam a música.
3. **Conflitos entre as mãos:** procurar notas sustentadas que passam a conflitar
   quando o acorde muda, sobreposições e cruzamentos de registro.
4. **Ritmo:** medir se o encaixe na grade alonga notas de passagem, antecipa mudanças
   de acorde ou remove o balanço. Avaliar síncope, swing e rubato separadamente.
5. **Voicing:** avaliar condução das vozes e posição dos acordes. Um acorde fechado
   pode continuar pesado, repetitivo ou mal conectado ao seguinte.
6. **Execução do piano:** testar dinâmica, acentuação, articulação e pedal depois
   de conferir as notas. Um timbre mais agradável não deve mascarar erro harmônico.

### Como investigar

- Usar frases de 10–30 segundos com voz, baixo, restante dos instrumentos e arranjo
  de piano alinhados na mesma linha do tempo.
- Anotar os problemas por categoria e guardar o antes/depois de cada intervenção.
- Comparar a extração automática com pequenos trechos revisados manualmente.
- Observar notas fortes e longas, posição métrica e resolução da dissonância.
- Usar detecção independente de altura nos casos duvidosos, como na investigação
  CREPE/pYIN, sem tratar concordância entre detectores como verdade musical absoluta.

**Cuidado metodológico:** não classificar toda nota fora do acorde ou da escala como
erro. Notas de passagem, apojaturas, antecipações, cromatismos, blue notes e tensões
podem ser intencionais. A avaliação precisa considerar duração, função e resolução.

### Entrega

Um relatório com casos reais, causas prováveis, evidências e mudanças propostas.
Cada proposta deve indicar qual problema resolve e quais notas legítimas pode afetar.
Essa investigação alimentará as regras da frente 3.

## 4. Frente 2 — criação de introduções e acompanhamentos

### Separar recuperação de criação

Hoje os Híbridos podem recuperar material instrumental que uma IA já extraiu da
gravação. A nova função deve também conseguir **criar** material que não estava ali.
O resultado precisa indicar sua origem: transcrito, recuperado ou gerado.

### 4.1 Introdução gerada

Proposta inicial: gerar introduções curtas de dois ou quatro compassos, orientadas
pelo tom, andamento, métrica e acorde de entrada da música. Avaliar outras durações
somente se houver necessidade musical demonstrada.

Possíveis estratégias a comparar:

- Apresentar um fragmento reconhecível da melodia, com acompanhamento simples.
- Usar um arpejo ou padrão rítmico construído com a harmonia inicial.
- Criar uma preparação harmônica que resolva de forma convincente no início da música.

Requisitos:

- Respeitar alcance, polifonia e ritmo permitidos pela dificuldade.
- Entrar no primeiro trecho sem mudança brusca de registro, dinâmica ou pulso.
- Não substituir uma introdução original bem transcrita por padrão mais genérico
  sem uma escolha explícita ou evidência de melhoria.
- Registrar a seção criada, sua duração e os parâmetros usados para reproduzi-la.
- Identificar no visualizador e nos arquivos que a introdução foi gerada.

### 4.2 Acompanhamento mais elaborado

Criar variações a partir dos acordes, baixo, melodia e arranjos já disponíveis.
Investigar padrões como acordes sustentados, arpejos, baixo alternado e figuras
sincopadas, escolhidos conforme a música e a atividade da melodia.

O objetivo é aumentar expressividade e continuidade, não apenas quantidade de notas.
Durante frases vocais densas, o acompanhamento pode simplificar; em intervalos
instrumentais, pode assumir mais movimento e motivos melódicos.

Cada variação deve passar pelas verificações de harmonia, alcance, velocidade de
salto, colisão entre mãos e clareza da linha principal. Considerar articulação,
dinâmica e pedal como componentes do arranjo.

### 4.3 Reprodutibilidade e interface

- Salvar a semente e os parâmetros quando houver aleatoriedade.
- Oferecer inicialmente uma ação simples, como **Criar introdução**, dentro de
  personalização. Evitar um painel com muitos padrões e controles numéricos.
- Uma eventual ação **Outra variação** deve gerar uma alternativa controlada e
  comparável, mantendo o resultado anterior disponível.
- O padrão continua conservando o material original quando ele já está adequado.

### 4.4 Linha do tempo

Uma introdução criada acrescenta tempo à partitura e à prévia de piano, mas não à
gravação original. O mapeamento precisa ser explícito: a seção criada não tem
correspondência no áudio original. Guardar o ponto em que a música original começa.
Esse requisito deve ser resolvido junto da frente 4.

### Critérios de aprovação

Demonstrar transição de entrada coerente, execução possível no nível e preferência
em comparação cega com uma alternativa simples. Guardar exemplos em que a criação
piora o resultado para evitar ativá-la indiscriminadamente.

## 5. Frente 3 — tornar a harmonia do arranjo mais coerente

Esta frente implementa as melhorias aprovadas pela investigação da frente 1.

### Modelo de contexto musical

Representar, por trecho, a tonalidade provável e sua confiança, os acordes e baixos,
as posições métricas, a atividade vocal e as fronteiras de frase/seção. Considerar
mais de uma hipótese quando a evidência for ambígua.

### Mudanças a testar

1. Estabilizar a sequência de acordes sem apagar mudanças reais e acordes de passagem.
2. Alinhar mudanças harmônicas com eventos musicais relevantes, em vez de depender
   exclusivamente de janelas fixas.
3. Escolher inversões e voicings pela sequência inteira, preservando vozes comuns
   e evitando movimento desnecessário.
4. Tratar colisões com a melodia. Preferir ajustar uma voz do acompanhamento quando
   a nota melódica estiver bem apoiada; revisar a própria melodia quando sua extração
   for incerta. Não deslocar uma nota correta apenas para caber na cifra estimada.
5. Controlar notas sustentadas durante mudanças de acorde, além das notas atacadas
   simultaneamente. Considerar o efeito do pedal e da cauda do som.
6. Preservar tensões e resoluções expressivas compatíveis com o estilo e o nível.
7. Aplicar restrições de dificuldade sem confundir fechamento de oitavas com correção
   de harmonia: mudar registro conserva classes de altura e não corrige um acorde errado.

### Regras de decisão

Toda alteração automática deve registrar motivo e confiança. Evidência forte da
gravação deve ter prioridade sobre uma regra genérica de escala. Em caso de dúvida,
preferir uma intervenção pequena e auditável a uma rearmonização extensa.

### Critérios de aprovação

- Menos erros confirmados nos trechos anotados, sem apagar tensões válidas dos controles.
- Preservação da melodia principal e de suas entradas importantes.
- Melhora ou manutenção de tocabilidade e coerência de frase.
- Resultado aceitável em músicas novas, além das usadas para ajustar os parâmetros.
- Avaliação auditiva favorável ou inconclusiva explicitamente registrada; não declarar
  melhora de naturalidade apenas porque aumentou a coincidência com cifras automáticas.

## 6. Frente 4 — melhorar o visualizador

### Leitura e navegação

- Refinar a barra contínua em mudanças de sistema/página, pausas, notas ligadas,
  zoom e telas estreitas. Ela deve permanecer ligada ao relógio da reprodução.
- Permitir repetir um trecho A–B e navegar por compasso/frase, com controles simples.
- Preservar a posição de reprodução ao comparar versões quando houver mapeamento
  temporal confiável. Não usar o mesmo número de segundos em arranjos com origens diferentes.
- Avaliar foco no sistema atual, realce da letra cantada, tamanho das notas e uso no celular.
- Oferecer rolagem manual previsível: acompanhar automaticamente deve continuar sendo opcional.
- Manter PDF, MusicXML e MIDI fáceis de encontrar sem competir com a área de leitura.

### Sincronia com a gravação original

Persistir as batidas reais, fase, deslocamento do arranjo e origem das seções.
Usar esse mapa para converter entre tempo da gravação e posição na partitura.
Uma simples diferença fixa de segundos não cobre rubato nem introduções acrescentadas.

Definir comportamento para seções criadas: o original pode começar somente ao
terminar a introdução gerada, com indicação clara desse trecho na interface.

### Confiabilidade

- Conferir sincronização com ataques audíveis, incluindo possível atraso de codificação
  e decodificação do MP3, não apenas com os tempos do MIDI.
- Testar busca para frente/trás, reprodução pausada, final da música, troca de versão,
  mudanças de andamento e redimensionamento durante reprodução.
- Manter uma fonte musical comum para PDF, SVG, MIDI e áudio, com identificação estável
  dos eventos e invalidação de cache quando o resultado muda.
- Medir fluidez e latência no desktop e em celular. Definir o limite de atraso visual
  após um piloto, com medidas de percentil e casos de teste reproduzíveis.

### Entrega

Um fluxo de ouvir/acompanhar/repetir/baixar validado em tarefas reais, com testes
automatizados das transições e inspeção visual em tamanhos diferentes.

## 7. Frente 5 — japonês e outros idiomas, com apresentação de karaokê

### Objetivo

Exibir o texto no idioma original, alinhado ao canto e às notas. O japonês exige
trabalho específico; adicionar uma opção `ja` ao seletor não resolve segmentação,
leitura de kanji, alinhamento e fontes.

### Etapas para japonês

1. Confirmar o idioma em regiões cantadas e testar músicas com japonês e inglês misturados.
2. Avaliar a transcrição no idioma original e o uso de letra oficial quando disponível.
3. Separar o texto exibido da representação fonética usada para alinhar o canto.
   Kanji e kana podem ser preservados na exibição, enquanto uma leitura em kana
   auxilia o alinhamento. Leituras ambíguas precisam de tratamento explícito.
4. Investigar segmentação adequada ao canto, considerando moras, vogais prolongadas,
   nasal, consoantes geminadas e melismas. Não assumir uma mora por nota nem usar
   separação por espaços como se fosse português.
5. Comparar a abordagem atual com alinhamento forçado em áudio cantado. Verificar
   quais ferramentas realmente suportam japonês, Windows e o orçamento de memória.
6. Implementar destaque progressivo da letra com os tempos resultantes.
7. Avaliar furigana/leitura em kana e romaji como recursos opcionais. A tela principal
   deve ter uma apresentação clara, sem mostrar três transcrições simultaneamente.

### Fontes e exportação

Verificar cobertura de kanji, hiragana, katakana e pontuação em SVG, PDF e navegador.
Evitar caracteres ausentes, texto cortado e dependência de fonte instalada somente
na máquina de desenvolvimento. Definir fontes compatíveis com exportação/distribuição.

### Testes

Usar trechos revisados de músicas lentas, rápidas e com idiomas misturados. Medir
cobertura textual, omissões/repetições e erro temporal por unidade alinhada. Avaliar
se a letra acompanha a interpretação real, não apenas se o texto está reconhecível.
Incluir revisão por alguém que compreenda japonês para validar leitura e segmentação.

Depois de consolidar a arquitetura de texto exibido/leitura/alinhamento, avaliar
outros idiomas sem presumir que a mesma regra de sílaba se aplique a todos.

## 8. Frente 6 — testar as alternativas e reduzir opções

### Pergunta de produto

Quais decisões o sistema já consegue tomar melhor do que um usuário que apenas
quer tocar a música? Modelos, variantes técnicas e estilos numerados devem sair do
fluxo principal quando houver evidência suficiente para escolher um padrão.

### Interface desejada

Fluxo principal: **música → dificuldade → gerar**. Proposta inicial de dificuldade
padrão: Médio, a confirmar em testes de uso.

Uma versão principal por nível e opções criativas compreensíveis, como introdução
gerada, podem ficar em **Personalizar**. Alternativas de modelo e parâmetros de
engenharia podem continuar disponíveis para avaliação interna/uso avançado, sem
obrigar o usuário comum a escolher entre cinco famílias e 21 estilos.

Se o melhor resultado variar por música/estilo, investigar uma escolha automática
com fallback. Não transformar toda exceção em mais um botão para o usuário decidir.

### O que significa demonstrar que X é melhor que Y

Separar três tipos de evidência:

| Tipo | Exemplos | Conclusão permitida |
|---|---|---|
| Verificação objetiva | igualdade MIDI/partitura, saltos, alcance, tempo, memória, erro temporal contra anotações | X apresenta menos erros ou menor custo nas condições medidas. |
| Fidelidade musical | alturas/acordes/entradas revisados, erros harmônicos confirmados, preservação da melodia | X se aproxima mais da referência avaliada naquele conjunto. |
| Percepção | preferência cega, naturalidade, reconhecimento da música, facilidade para tocar | Os avaliadores preferiram X, com a incerteza e o perfil da amostra informados. |

Não existe um único número que prove superioridade musical universal. A escolha
do padrão deve combinar requisitos verificáveis com preferência avaliada de forma
controlada. Quando a diferença não for demonstrável, registrar empate/inconclusão
e considerar custo e simplicidade como critérios de decisão.

### Protocolo experimental

1. Congelar uma versão do código, modelos, parâmetros e entradas intermediárias:
   stems, batidas, notas, qualidades e palavras. Não reexecutar Whisper ou extração
   vocal entre dois candidatos que deveriam diferir somente no acompanhamento.
2. Manter tom, trecho, andamento, nível e sintetizador comparáveis. Controlar o
   volume para não confundir maior intensidade com melhor arranjo.
3. Comparar um fator por vez. Investigar também o efeito de remover uma regra,
   para descobrir quais partes da melhoria são responsáveis pelo resultado.
4. Separar desenvolvimento e avaliação por música; trechos da mesma composição
   não devem aparecer dos dois lados da divisão. Evitar selecionar apenas os casos
   que favorecem o algoritmo proposto.
5. Usar as oito músicas atuais e os três problemas conhecidos como regressão.
   Acrescentar músicas novas, gêneros diferentes e japonês para avaliar generalização.
6. Começar com um piloto de tamanho viável, por exemplo 12–20 músicas. Estimar
   variabilidade e tamanho de efeito antes de decidir se a amostra basta. Esse
   número inicial é planejamento, não garantia de comprovação estatística.
7. Fazer comparações A/B cegas, com ordem aleatória e nomes de modelo ocultos.
   Perguntar separadamente por naturalidade, fidelidade e tocabilidade.
8. Tratar música como unidade de comparação; muitos compassos da mesma música não
   equivalem a muitas músicas independentes. Informar intervalos de incerteza e
   resultados por gênero/nível, além das médias.
9. Repetir inferências quando houver variabilidade relevante e salvar sementes/
   snapshots. Um único resultado estocástico não deve definir o padrão do aplicativo.
10. Definir requisitos, métricas principais e critérios de escolha antes de olhar
    os resultados finais. Não inventar pesos posteriormente para favorecer um candidato.

### Métricas a manter no relatório

- Alturas, ataques, durações, ligações e correspondência entre partitura/MIDI.
- Erro de altura/oitava contra referência revisada; taxa de alteração indevida de
  cromatismos e ornamentos válidos nos controles.
- Erros harmônicos confirmados, condução de vozes e sustentação durante mudanças.
- Alcance simultâneo por mão, saltos com tempo disponível, densidade e pico de ataques.
- Cobertura e tempo das letras, separados por idioma.
- Continuidade e transição das introduções, distinguindo criação de recuperação.
- Tempo de execução, memória, falhas e tamanho dos resultados.
- Preferência cega e taxa de conclusão das tarefas na interface.

Coerência com cifras automáticas e concordância com a melodia automática continuam
úteis para diagnóstico, mas não servem sozinhas como prova de correção.

### Regra para simplificar o produto

Uma alternativa só vira padrão se passar pelas verificações obrigatórias e
demonstrar vantagem relevante no conjunto reservado à avaliação, sem regressões
graves escondidas pela média. Se duas alternativas forem equivalentes dentro da
incerteza, preferir a mais simples, rápida e estável.

Depois disso, retirar a escolha técnica do fluxo principal e manter a decisão
documentada: versões comparadas, dados, critérios, resultado e limitações.

## 9. Ordem recomendada de execução

| Fase | Trabalho | Entrega que permite avançar |
|---|---|---|
| 0 | Congelar entradas e montar benchmark/regressões | Execução reproduzível e exemplos comparáveis. |
| 1 | Investigar naturalidade e erros harmônicos | Catálogo de causas e referências revisadas. |
| 2 | Implementar coerência harmônica e condução de vozes | Melhoria validada sem destruir notas legítimas. |
| 3 | Refinar visualizador e persistir os mapas de tempo | Reprodução/navegação confiáveis e base para original/intro gerada. |
| 4 | Prototipar introduções e acompanhamentos criativos | A/B controlado, transição de entrada e limites de dificuldade. |
| 5 | Implementar japonês com alinhamento e fontes | Trechos revisados funcionando no app e nas exportações. |
| 6 | Consolidar comparações e simplificar a interface | Um padrão confiável por nível e fluxo principal curto. |

As frentes podem compartilhar infraestrutura, mas não colocar todos os experimentos
na interface ao mesmo tempo. O benchmark começa primeiro e acompanha cada fase.
Testes de uso podem acontecer antes da fase 6; a retirada definitiva de escolhas
técnicas depende dos resultados.

## 10. Critérios gerais para considerar a etapa concluída

- Harmonia avaliada contra exemplos revisados, com casos legítimos de dissonância preservados.
- Introduções criadas identificadas e transições testadas; acompanhamento mais elaborado
  continua compatível com a dificuldade.
- Visualizador acompanha reprodução, pausas, busca e mudanças de seção de forma previsível.
- Japonês validado além da mera exibição de caracteres, incluindo leitura e tempo do canto.
- Interface principal reduzida às decisões que o usuário precisa tomar.
- Padrões escolhidos por evidências publicadas no relatório, com incerteza explícita.
- PDFs, MusicXML, MIDI e prévias continuam correspondentes.
- Exemplos A/B e dados suficientes para reproduzir a comparação são mantidos no projeto.

## 11. Primeira tarefa concreta da próxima sessão

Preparar o benchmark e investigar alguns conflitos harmônicos reais antes de
introduzir geração criativa. Escolher trechos conhecidos e novos, congelar os
intermediários, anotar as referências e comparar:

1. Pipeline atual como controle.
2. Mesmo pipeline com correções harmônicas pequenas e explicáveis.
3. Alternativas atuais de acompanhamento sob as mesmas condições.

A entrega inicial deve ser um relatório de causas e uma tabela de comparação,
com exemplos audíveis. A partir dele, decidir quais regras implementar e quais
opções o usuário deixará de precisar escolher.

## 12. Experimento anotado: separação em 6 faixas (`htdemucs_6s`) — 2026-11-10

Origem: o usuário achou o Moseca (github.com/fabiogra/moseca, MIT), interface Streamlit em
volta do Demucs que separa voz, bateria, baixo, guitarra, piano e "resto". Não precisa do
Moseca: o modelo `htdemucs_6s` já vem no pacote `demucs` que a partitura usa
(`python -m demucs -n htdemucs_6s`). Ressalvas: o próprio Demucs avisa que a faixa de piano
tem bastante vazamento e artefatos, e o modelo é mais lento que o `htdemucs`.

**Hipóteses a testar (na Windows, com GPU e a biblioteca):**

1. **Acordes mais limpos.** Hoje `acordes()` usa a faixa "resto" (teclado, guitarra, sopro,
   cordas, efeitos misturados) + 0,3 × baixo. Com 6 faixas, usar guitarra + piano (+ baixo)
   como harmonia deve reduzir ruído na detecção de acordes e nas cifras.
2. **Piano da gravação no acompanhamento.** Em música com piano de verdade, transcrever a
   faixa de piano e oferecer uma versão com ele na esquerda (ao lado de Pop2Piano/AMT-APC).

**Protocolo:**

- Músicas: 2-3 da biblioteca com piano ou violão bem presentes, mais 1 sem (controle).
- Separar com `htdemucs` e `htdemucs_6s` e ouvir as faixas de piano e guitarra.
- Acordes: rodar `acordes()` com "resto" e com guitarra+piano; comparar com cifras de
  referência conferidas à mão em 3-4 trechos (concordância por janela de 2 tempos, nº de
  trocas espúrias). Medir também `harmonia_estimada` do `analisar_completo.py`.
- Piano: se a faixa vier limpa, transcrever e montar a versão; julgar às cegas na página
  de comparação (mesmo piano, partitura visível, "onde muda").
- Custo: tempo de separação das duas variantes.

**Decisão:** só trocar o padrão se a concordância dos acordes melhorar nos trechos
conferidos sem piorar o controle, e se a avaliação cega preferir; senão fica como opção
(`--seis-faixas`) ou é descartado, com o resultado registrado aqui.

**Pronto pra rodar (2026-11-10):** `gerar.py --separador htdemucs_6s` (acordes com
guitarra + piano + 0,5 × resto quando as faixas existem) e
`python experimento_6faixas.py entrada\a.wav entrada\b.wav [--referencias pasta]`
(referência: `<pasta>/<nome>.csv` com linhas `inicio_s,fim_s,acorde`, ex. `12.5,14.0,Am7`),
que gera relatório, JSON e página em `trabalho/experimento_6faixas/`.
