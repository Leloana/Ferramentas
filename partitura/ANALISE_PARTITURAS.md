# Análise e revisão das partituras — 9/10 de novembro de 2026

## Escolha da versão principal

| Nível | Principal | Motivo |
|---|---|---|
| Fácil | **Acordes** | Linha cantada com letra e baixo simples; menor atividade da esquerda. |
| Médio | **Híbrido AMT** | Melodia e letra, acompanhamento da IA e trechos instrumentais, com acordes fechados e menos saltos. |
| Difícil | **Híbrido AMT** | Preserva a linha cantada e acrescenta os instrumentais. AMT-APC completo fica como alternativa de cover instrumental, sem letra. |

A recomendação do Difícil mudou depois da revisão. Antes, a seleção era AMT-APC,
favorecendo o cover instrumental. Com as introduções nos Híbridos, o Híbrido AMT
atende melhor ao objetivo do projeto: tocar piano com a melodia e a letra da música.
As estrelas e a seleção ao mudar de nível já foram atualizadas na interface.

## Escopo e método

Analisadas **117 partituras antes e 120 depois**, de oito músicas, cinco versões e
três níveis. No Surprises passou de 12 para 15 ao receber o Pop2Piano completo.
A pasta antiga `No Surprises`, com apenas o original, não entra na contagem.

Comparam-se Acordes, Híbrido Pop2Piano, Híbrido AMT, Pop2Piano e AMT-APC.
As prévias de estilos alternativos de Baby não têm conjuntos equivalentes de
partituras por nível; não há evidência suficiente para declarar um desses estilos
o melhor global. O estilo 1 continua como padrão.

`analisar_completo.py` mede notas e ataques por segundo, pico em dez segundos,
polifonia, abertura simultânea, saltos, notas curtas, mudanças de armadura, harmonia
estimada e concordância com a melodia. Considera notas sustentadas junto com novos
ataques, além de reunir ligações **por nota**, inclusive em acordes parcialmente ligados.

As médias dão o mesmo peso a cada música. Na comparação anterior, Pop2Piano tinha
sete músicas; agora todas as versões têm oito. As duas séries não são exatamente
pareadas para esse modelo. A comparação AMT/Híbrido AMT tem oito músicas nas duas.

O alinhamento temporal entre versões usa as cifras: o exportador pode começar cada
versão em um compasso diferente conforme o primeiro evento da esquerda. Comparar
os tempos sem esse ajuste produz resultados melódicos incorretos.

**Limites da avaliação:** a referência melódica é a extração vocal do próprio
pipeline, não uma transcrição humana. Concordância de 100% significa preservar
essa referência, não acertar 100% da gravação. Harmonia é compatibilidade com as
cifras estimadas pelo pipeline; Acordes tem vantagem por ser construído delas.
Notas de passagem e tensões podem ser musicais mesmo fora dessas cifras.
Esta é uma análise estrutural, com testes de reprodução/sincronia; não houve uma
avaliação auditiva completa nem revisão humana de todas as páginas.

## Resultado atual

Notas/s contam notas individuais; ataques/s contam movimentos no tempo. Três notas
de um acorde simultâneo não equivalem a três movimentos sucessivos.

| Nível | Versão | Notas/s direita / esquerda | Aberturas > oitava D / E | Concordância melódica |
|---|---|---:|---:|---:|
| Fácil | **Acordes** | 1,25 / 0,57 | 0% / 0% | 100% (referência) |
| Fácil | Híbrido AMT | 1,37 / 0,95 | 0% / 0% | 100% |
| Fácil | Híbrido Pop2Piano | 1,37 / 0,87 | 0% / 0% | 100% |
| Fácil | AMT-APC | 1,39 / 0,96 | 0% / 0% | 38% |
| Fácil | Pop2Piano | 1,39 / 0,87 | 0% / 0% | 33% |
| Médio | **Híbrido AMT** | 2,09 / 1,48 | 0% / 0% | 100% |
| Médio | Acordes | 1,90 / 2,92 | 0% / 0% | 100% |
| Médio | Híbrido Pop2Piano | 2,13 / 1,65 | 0% / 0% | 100% |
| Médio | AMT-APC | 2,61 / 1,49 | 0% / 0% | 55% |
| Médio | Pop2Piano | 2,80 / 1,65 | 0% / 0% | 49% |
| Difícil | **Híbrido AMT** | 2,58 / 1,41 | 0% / 0% | 100% |
| Difícil | AMT-APC | 2,61 / 1,42 | 0% / 0% | 61% |
| Difícil | Híbrido Pop2Piano | 2,62 / 1,84 | 0% / 0% | 100% |
| Difícil | Pop2Piano | 2,83 / 1,83 | 0% / 0% | 51% |
| Difícil | Acordes | 2,38 / 2,92 | 0% / 0% | 100% |

Tabela atualizada após a proteção vocal de 2026-11-10 em Para Machucar Meu Coração.
Essa proteção usa confiança, patamar estável e contexto antes da quantização;
os três exemplos indicados pelo usuário foram filtrados no Médio. Novas gerações
aplicam a regra a Acordes e Híbridos; as outras sete músicas ainda não foram regeneradas
com ela. Detalhes em `DIAGNOSTICO_CORACAO.md` e seção 13 do `HANDOFF.md`.

As 120 partituras ficaram sem aberturas simultâneas maiores que uma oitava.
A maior abertura encontrada foi **11 semitons**, em ambas as mãos. Isso remove
um obstáculo de alcance; não garante que todo trecho seja fácil de executar.

## Antes e depois

| Indicador | Antes | Depois |
|---|---:|---:|
| Híbrido AMT–Médio: aberturas grandes na esquerda | 11,4% | **0%** |
| Híbrido Pop2Piano–Médio: aberturas grandes na esquerda | 26,7% | **0%** |
| AMT–Difícil: aberturas grandes direita / esquerda | 9,6% / 11,4% | **0% / 0%** |
| Híbrido AMT–Médio: média do percentil 95 dos saltos da esquerda | 15,7 semitons | **9,7 semitons** |
| Híbrido AMT–Difícil: média do percentil 95 dos saltos da esquerda | 16,3 semitons | **10,5 semitons** |
| Híbrido AMT–Médio: mudanças de armadura nas oito músicas | 7 | **4** |
| Híbrido AMT–Difícil: mudanças de armadura nas oito músicas | 7 | **5** |

Os saltos acima são percentis calculados por música e depois promediados; não são
um teto garantido para cada salto. O algoritmo penaliza saltos rápidos conforme a
distância em tempos musicais entre ataques. Ainda falta calibrar limites físicos
em segundos para diferentes andamentos e tamanhos de mão.

Acordes–Médio tem 2,92 notas/s na esquerda, mas só 0,97 ataques/s: são acordes
simultâneos. Continua sendo uma alternativa boa para estudo, com saltos menores
(percentil 95 médio de 6,9 semitons), apesar de soar menos como um cover completo.

## O que mudou

1. **Aberturas:** revoicing por oitavas conserva classes de altura após a redução
   de notas por nível. A direita mantém a nota superior; a esquerda mantém a classe
   do baixo e escolhe o registro por programação dinâmica. Dobramentos de oitava
   redundantes são removidos. Isso pode deixar o som menos cheio, mas tocável.
2. **Saltos:** a escolha do registro considera a sequência de acordes, não apenas
   cada acorde isolado. Pausas/intervalos maiores permitem movimentos maiores.
3. **Instrumentais dos Híbridos:** a direita da IA preenche lacunas longas sem voz.
   No pipeline, notas vocais e tempos das palavras protegem o canto. Na revisão dos
   sete arquivos antigos, sem os tempos originais das palavras, foram acrescentados
   apenas intro/outro, protegendo toda a região cantada. No Surprises foi regenerada
   pelo pipeline completo, incluindo a proteção pelos tempos do Whisper.
4. **No Surprises:** Híbrido AMT ganhou 69/73/61 ataques instrumentais nos níveis
   Fácil/Médio/Difícil. Isso recupera material da direita que antes era descartado;
   a fidelidade do motivo inicial ainda precisa de avaliação auditiva.
5. **Garota e Rosa:** Acordes–Médio foi atualizado. Os arquivos antigos tinham
   respectivamente 83,3% e 55,9% de aberturas grandes; agora ambos têm zero.
6. **Armaduras:** a troca exige evidência mais forte (custo de 25% de um bloco típico,
   antes 12%). Modulações continuam possíveis. A redução observada não prova que
   toda armadura escolhida esteja musicalmente correta.
7. **Fácil:** novas gerações suavizam apenas ornamentos de até 180 ms entre duas
   notas iguais, sem alterar ataques de palavras. Não se força toda a música à
   escala. Essa regra usou os segundos originais em No Surprises; as outras músicas
   foram revisadas a partir dos MusicXML e não tiveram a melodia reextraída.

## Prévia e partitura sincronizadas

Confirmado o bug ouvido em No Surprises: cifras eram exportadas como acordes
adicionais no MIDI, apesar de `writeAsChord=False`. A versão Fácil antiga tinha
437 notas escritas e 688 no MIDI. O áudio antigo soava mais cheio do que a partitura.

A exportação agora lê as notas do MusicXML e reúne ligações por nota/voz. Cifras
continuam visíveis, mas não tocam como notas extras. Isso também corrige diferenças
nas ligações parciais de acordes. Os 120 MIDIs foram conferidos: **91.401 notas**,
sem diferença de altura, ataque ou duração, com tolerância de 5 ms para ticks MIDI.
O BPM original foi mantido nos MIDIs editáveis. Todas as prévias afetadas foram atualizadas.

O novo visualizador SVG destaca notas, mostra o cursor, acompanha a rolagem, permite
clicar numa nota para buscar e tem zoom. Usa IDs explícitos e tempos do MusicXML,
compartilhados com o MIDI. Não depende do relógio interno do Verovio, que mostrou
diferenças em arquivos com múltiplas vozes e ligações. A voz zero é renumerada para
o importador gráfico. O PDF permanece disponível para leitura e impressão.

O destaque acompanha **a prévia de piano**. Ao tocar o original, o piano pausa e o
destaque é limpo. Sincronizar a gravação original exige preservar o mapa de batidas
e o deslocamento temporal de cada versão; isso ainda não foi implementado.

Testes: oito testes de regras musicais/cache/exportação; auditoria dos 120 MIDIs;
checagem dos IDs e tempos visuais em sete partituras; Chrome no desktop e celular,
incluindo reprodução, busca, clique, zoom, exclusão entre players e recomendação do Difícil.

## Artefatos e pendências

- Atuais: `saida/analise_completa.json` e `saida/analise_resumo.json`.
- Antes: `trabalho/revisao_20261109/analise_antes.json` e `resumo_antes.json`.
- Backups dos PDFs, MusicXML, MIDIs e prévias anteriores na mesma pasta, por música.
- `analisar_completo.py --antes` refaz a análise dos backups; sem argumento analisa a biblioteca atual.
- `conferir_previa.py --todas` audita as notas dos MIDIs.

Continuam pendentes: alinhamento forçado da letra oficial, recuperação de palavras
não ouvidas, integração com o karaokê, sincronia com a gravação original e avaliação
auditiva dos motivos instrumentais. As melhorias de alcance não resolvem sozinhas
erros de transcrição, síncopes, rubato ou letras omitidas pelo Whisper.
