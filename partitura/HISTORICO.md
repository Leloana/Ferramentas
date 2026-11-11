# Histórico das sessões — Partitura

Crônica de cada sessão (o que foi feito, por quê, números e testes), em ordem. O estado atual,
as pendências e as pegadinhas estão resumidos no `HANDOFF.md`; este arquivo é a referência
detalhada. As seções 1–7 descrevem o estado de 2026-11-09 e parte delas foi superada depois.

Ferramenta que pega uma **música normal, com voz**, e gera **partitura de piano com a letra embaixo das notas**
(PDF + MusicXML + MIDI + prévia em áudio), com interface web e níveis de dificuldade.
**Tudo automático e local, sem LLM**: só modelos de áudio (Demucs, torchcrepe, Whisper, Pop2Piano, AMT-APC)
e regras musicais em código. Uso pessoal.

O README (`partitura/README.md`) descreve uso e números; este documento conta **o que foi feito, por quê, o que
quebrou no caminho e o que falta**.

---

## 1. Como rodar

```powershell
cd partitura
.\venv\Scripts\python.exe run.py                 # interface web: http://127.0.0.1:8030 (--lan pra rede local)

# linha de comando (tudo de uma música):
.\venv\Scripts\python.exe gerar.py entrada\musica.wav --titulo "Nome" --artista "Artista" `
    --nivel todos --hibrido --pop2piano --amtapc --idioma auto
.\venv\Scripts\python.exe analisar.py            # compara todas as partituras de saida/ (métricas)
```

Saída: `saida/<Título>/`
```
Original.mp3                       áudio de origem
<Versão> - <Nível>.pdf             ex.: "HibridoAMT - Medio.pdf"
<Versão> - <Nível> - previa.mp3    como a partitura soa, tocada num piano de cauda
editaveis/  .musicxml (MuseScore) e .mid
cache/      MIDIs brutos das IAs (pop2piano_bruto.mid, amtapc_<nivel>.mid)
meta.json   video_id, título, artista (a interface usa)
```

## 2. Arquitetura (arquivos)

| arquivo | papel |
|---|---|
| `gerar.py` | pipeline principal: Demucs → batidas → melodia (torchcrepe) → acordes → letra → níveis → music21 → Verovio → PDF (Chrome headless) → prévia (FluidSynth) |
| `letra.py` | Whisper `large-v3-turbo` (faster-whisper), detecção de idioma, filtros de alucinação + 2ª tentativa, letra oficial (LRCLIB), sílabas (pyphen), alinhamento sílaba→nota (programação dinâmica) |
| `niveis.py` | fácil/médio/difícil: grade rítmica, mão esquerda, cifra em tríades, redução de notas das IAs, transposição do fácil |
| `pop2piano.py` | Pop2Piano via `transformers` (`sweetcocoa/pop2piano`), quantização e divisão por mão, estilos `composer1..21` |
| `amtapc.py` | AMT-APC (repo de terceiros em `modelos/amt-apc`, chamado por subprocess com `python -X utf8`) |
| `_stubs/essentia/` | substituto mínimo do essentia (não tem build pra Windows): só entrega as batidas pro Pop2Piano |
| `analisar.py` | métricas objetivas das 105 partituras → `saida/analise.json` |
| `web/servidor.py` + `web/static/` | FastAPI: busca/prévia no YouTube (yt-dlp), fila de geração (1 trabalho por vez na GPU), biblioteca |
| `run.py` | sobe o uvicorn na porta 8030 |

Fora do git (`.gitignore`): `venv/`, `entrada/` (wav baixado), `trabalho/` (stems do Demucs), `saida/`,
`soundfonts/piano.sf2`, `ferramentas/fluidsynth/`, `modelos/amt-apc/`, `web/cache_previas/`.
Áudio e partituras ficam fora por direito autoral.

## 3. As versões e os níveis

**Versões**
- **Acordes** — melodia cantada + letra na mão direita; acordes detectados em bloco na esquerda.
- **Híbrido (Pop2Piano)** (`Hibrido`) — melodia cantada + letra; esquerda do Pop2Piano.
- **Híbrido (AMT)** (`HibridoAMT`) — melodia cantada + letra; esquerda do AMT-APC. Sai quando `--hibrido --amtapc`.
- **Pop2Piano** — arranjo completo da IA (2 mãos), sem letra.
- **AMT-APC** — arranjo completo da outra IA (2024), sem letra.

**Níveis** (`--nivel facil,medio,dificil|todos`)

| | Fácil | Médio | Difícil |
|---|---|---|---|
| ritmo | semínima | colcheia | semicolcheia |
| mão esquerda (Acordes) | só o baixo, segurado | baixo + 3ª e 7ª, fechado em 1 oitava | baixo + acorde em ritmo |
| IAs | 1 nota por mão | até 2 (esq.) / 3 (dir.) | completo |
| cifra | tríades | completa | completa |
| tom | armadura única, transposto pra sem acidentes | original (armadura muda por trecho) | original |

**Padrão atual por nível** (revisão da seção 10): **Fácil = Acordes · Médio = Híbrido (AMT) · Difícil = Híbrido (AMT)**.
AMT-APC completo continua disponível como cover instrumental sem letra.
A interface marca com ★ e pula pra ela ao trocar de nível.

## 4. Linha do tempo do que foi feito

1. **Pipeline base**: Demucs (`htdemucs`) separa; torchcrepe extrai a melodia da voz; acordes por chroma +
   Viterbi; MusicXML → PDF com Verovio + Chrome. Teste com *Chega de Saudade* (Tom Jobim).
   - A 1ª gravação do Jobim era **instrumental** (voz a −75 dB): troquei pela ao vivo em Montreal.
2. **Correções de notação**: armadura por trecho (Ré menor → maior), grafia guiada pelo acorde (A7 = C♯, não D♭),
   grade em colcheia (semicolcheia poluía), bequadro saindo nas cifras, cp1252 embaralhando o texto do Verovio.
3. **Pop2Piano** (arranjo de IA). Precisou do stub do essentia. Usuário: "o Pop2Piano parecia mais a música" →
   criei o **Híbrido** (melodia cantada + acompanhamento da IA).
4. **Letra embaixo das notas**: Whisper com tempo por palavra, pyphen pra sílabas, alinhamento global.
   - Alucinação em loop ("quatro, quatro, quatro…") → filtros por compressão/repetição.
   - Inglês: sílabas com borda 2 (sem "friend-s").
5. **Músicas testadas**: Chega de Saudade (Jobim, Montreal), Bandido com Bandida (DPAULA, Nanda Tsunami,
   ERICONESS), Baby (Justin Bieber), Quando a Sorte (Chico Chico), Para Machucar Meu Coração (Getz/Gilberto),
   Garota de Ipanema (João Gilberto), Rosa de Hiroshima (Secos e Molhados — pedida pelo usuário na interface).
6. **Saída organizada** por música + `Original.mp3`.
7. **Prévia com piano de verdade**: o sintetizador de senoides era "ardido, eletrônico". Agora FluidSynth 2.6.2
   + SoundFont Steinway NY Model B ("Dore Mark's NY S&S Model B v5.2", coleção soundfonts4u via HuggingFace).
   O usuário autorizou rodar o `fluidsynth.exe`.
8. **Níveis de dificuldade** (fácil/médio/difícil). A transposição do fácil errou de início (foi pra Dó menor,
   3 bemóis); refeito: armadura única + transposição que zera a armadura.
9. **Interface web** (busca no YouTube estilo karaokê, fila com progresso, biblioteca com PDF/prévia/original).
10. **Idioma**: o Whisper detectava pelo início (introdução) e **traduzia** Garota de Ipanema pro inglês.
    Agora vota em 6 janelas com voz; voto dividido → modo multilíngue.
11. **Estilos do Pop2Piano** (`--estilo 1-21`): o `composer1` (padrão) quase não toca baixo (19% de graves).
    Amostras em `saida/Baby/estilos_pop2piano/`.
12. **AMT-APC** (2024, `310hz/amt-apc`): ~7 s por música (Pop2Piano ~30 s). Precisa de `python -X utf8` no
    Windows. Os "levels" dele **não são dificuldade** (o level1 gera mais notas que o Pop2Piano) → passa pela
    mesma redução. Usuário ouviu: "melhores em alguns casos, mais tocáveis" → **Híbrido (AMT)**.
13. **Bug da interface** que o usuário bateu: Enter no diálogo acionava o 1º botão ("Cancelar") e o pedido sumia
    sem aviso. Corrigido (Enter = gerar, aviso de "entrou na fila") + cabeçalho `no-cache` e `?v=N` nos assets
    (o navegador rodava o JS velho).
14. **Letra mais robusta** (descoberto em Rosa de Hiroshima):
    - **letra oficial automática no LRCLIB** (título + artista), usada só pra **corrigir a grafia** depois —
      como *prompt* ela fazia o Whisper misturar versos;
    - **2ª tentativa**: trecho descartado como alucinação ("A CIDADE NO BRASIL") é transcrito sozinho e
      costuma sair certo (recuperou o 1º verso de Rosa; 59 palavras em Baby);
    - várias sílabas numa nota viram **notas repetidas** na mesma altura.
15. **Análise das 105 partituras** e padrão por nível (seção 6). Achou e corrigiu: Acordes-Médio com 64% dos
    acordes abertos > oitava.

## 5. Decisões e pegadinhas (importante pra quem continuar)

- **Windows / acentos**: Verovio `loadFile` falha com acento no caminho → usar `loadData(texto)`.
  O AMT-APC abre arquivos sem encoding → `python -X utf8`. Prints com `PYTHONIOENCODING=utf-8`.
- **Módulo duplicado**: `gerar.py` roda como `__main__`; quem faz `import gerar` pega **outra cópia** com
  `SR_GRADE` padrão. Por isso o passo da grade viaja no objeto `Grade` (`grade.passo`). Não volte a ler
  `gerar.SR_GRADE` de outro módulo.
- **faster-whisper**: o leitor de áudio (PyAV) quebra com versões novas do `av` → passar o áudio já carregado
  (librosa, 16 kHz). `vad_filter=False` (o VAD corta canto). A letra oficial **não** vai como `initial_prompt`.
- **Loops de shell**: `while read ... done <<EOF` com Python dentro → o Python consome o stdin. Usar `< /dev/null`.
- **curl no Windows** manda acento em cp1252 → JSON inválido; testar a API com Python/urllib.
- **Permissões**: executar código baixado de terceiros (fluidsynth.exe, repo do AMT-APC) é bloqueado pelo
  classificador até o usuário autorizar explicitamente. Ambos já foram autorizados nesta sessão.
- **Etude** (piano cover, set/2025, diz superar AMT-APC/PiCoGen2): descartado — pede 16 GB de VRAM (a RTX 4070
  tem 12) e Linux + conda.
- **Pop2Piano** só funciona com o stub `_stubs/essentia` no `sys.path` antes do `transformers`.

## 6. Resultado da análise (`analisar.py`, 7 músicas)

| nível | versão | notas/s dir. | notas/s esq. | abertura > 8ª | harmonia | melodia cantada |
|---|---|---|---|---|---|---|
| Fácil | **Acordes** ★ | 1,3 | 0,5 | 0% | 58% | própria |
| Médio | **Híbrido (AMT)** ★ | 2,0 | 1,9 | 12% | 64% | própria |
| Médio | Híbrido (Pop2Piano) | 1,9 | 1,7 | 26% | 57% | própria |
| Difícil | **AMT-APC** ★ | 3,7 | 1,9 | 11% | 70% | 25% |
| Difícil | Pop2Piano | 2,9 | 1,9 | 23% | 63% | 30% |

- AMT-APC > Pop2Piano em tocabilidade (metade das aberturas) e coerência harmônica (+7 pontos).
- Nenhuma IA carrega a melodia cantada (25–30%): pra cantar junto, só versões com melodia + letra.
- Letra não depende do nível. Cobertura da letra oficial: 86% Rosa, 74–75% Baby/Bandido, 58% Para Machucar,
  ~48% nas bossas ao vivo (trechos sussurrados; a letra oficial de Garota inclui a versão em inglês).
- A 1ª rodada da análise dizia "35% de letra": era bug do analisador (lia sílabas sem o `syllabic` do MusicXML).

## 7. Estado ao fim da sessão

- Tudo commitado e enviado (`main`). Último commit de código: `518ab3a`.
- Biblioteca: 7 músicas × 5 versões × 3 níveis em `saida/`.
- **Em andamento quando este handoff foi escrito**: regeneração do nível **Médio** das 7 músicas com o novo
  voicing fechado do Acordes + nova rodada do `analisar.py`. Se `Acordes - Medio` ainda mostrar aberturas
  grandes, é porque essa rodada não terminou — rode de novo.
- Servidor web estava rodando em segundo plano na porta 8030 (fila de trabalhos fica só na memória).

## 8. Pendências / próximos passos

1. **Fácil com muitos acidentes** (~24% das notas da melodia cantada): alinhar notas curtas cromáticas à escala.
2. **Palavra no começo do verso some** quando o detector de melodia não pega a nota de ataque
   (ex.: "Pensem" no 2º/3º verso de Rosa). Ideia: usar o ataque da sílaba (Whisper) pra criar a nota que falta.
3. **Armadura troca demais** em músicas que modulam (Garota de Ipanema no Híbrido): aumentar o custo de troca
   ou trocar só em fronteira de seção.
4. **Escolha de estilo do Pop2Piano na interface — implementada nesta continuação**: seletor 1–21,
   ativo quando Híbrido (Pop2Piano) ou Pop2Piano está marcado. API valida o intervalo, passa `--estilo`
   ao pipeline e salva `estilo_pop2piano` no meta.json. Mantido o padrão 1; o usuário ainda não escolheu outro.
5. **Alinhamento forçado da letra oficial** (como o karaokê faz com MMS_FA) em vez de Whisper + correção:
   resolveria trechos perdidos nas bossas.
6. **Integração com o karaokê**: gerar partitura direto das músicas da biblioteca (stems e letra alinhada já existem).
7. Rap/trap (Bandido com Bandida): melodia é aproximada (voz meio falada) — esperado.
8. "The girl from Ipanema" alucinado no início de Garota (não é caixa alta, passa no filtro).

## 9. Continuação de 2026-11-09 — No Surprises e pendências

- Corrigido `melodia()` em gerar.py: o CREPE pode retornar um frame além das amostras disponíveis.
  `mean([])` nesse frame gerava NaN; o percentil do volume virava NaN e descartava TODAS as notas.
  Agora o cálculo RMS preenche o final com zeros. Validação na voz de No Surprises: 488 notas sem
  subdivisão por ataques; execução completa pela interface: 483 notas, antes zero.
- `eventos_melodia_acordes()` agora informa claramente quando não há notas, antes de median/max.
- Servidor iniciado em segundo plano; stdout/stderr em `servidor.stdout.log` e `servidor.stderr.log`.
  O log por pedido continua só na memória.
- No Surprises terminou e foi revisada novamente na seção 10. O seletor de estilos foi ativado após reinício.
- Conferência dos MusicXML existentes, sem regeneração: Acordes–Médio tem abertura > oitava de 0%
  em Baby, Bandido com Bandida, Chega de Saudade, Para Machucar Meu Coração e Quando a Sorte.
  **Ainda falta regenerar Garota de Ipanema (83,3%) e Rosa de Hiroshima (55,9%) no nível Médio**
  e atualizar `saida/analise.json`. Não disputar a GPU com a geração atual.
- Validação: sintaxe JS (`node --check`), parsing Python, API aceita estilos 1 e 21, padrão 1,
  rejeita 0 e 22. Não houve teste visual do seletor no navegador.

## 10. Revisão completa e visualizador sincronizado

Pedidos do usuário: refazer a análise dos modelos/partituras, corrigir divergência entre
prévia e PDF de No Surprises, recuperar a introdução instrumental, executar melhorias e
mostrar na partitura o momento atual do áudio. Autorizou seguir autonomamente.

### Estado entregue

- Biblioteca atual: **8 músicas × 5 versões × 3 níveis = 120 partituras**, PDFs/MusicXML/MIDI/prévias atualizados.
- No Surprises ganhou o Pop2Piano completo e os Híbridos receberam direita instrumental
  nas lacunas sem voz. No Híbrido AMT foram +69/+73/+61 ataques nos três níveis.
- Nas outras sete músicas, revisão dos MusicXML preservou melodia/letra existentes;
  introduções/outros foram acrescentados a partir das versões completas. Sem tempos
  originais das palavras, a região cantada foi toda protegida; não se preencheram interlúdios internos.
- Acordes–Médio de Garota e Rosa finalmente revisados: aberturas grandes passaram de
  83,3%/55,9% a zero. **As 120 partituras têm zero aberturas > oitava**, máximo medido de 11 semitons.
- No Híbrido AMT–Médio, a média do percentil 95 dos saltos da esquerda caiu de 15,7 a 9,7
  semitons; no Difícil, de 16,3 a 10,5. Não é um teto para cada salto.
- Principais na interface: Acordes/Fácil, Híbrido AMT/Médio e **Híbrido AMT/Difícil**.
  O Difícil mudou para preservar melodia/letra agora que também há instrumentais.
- Servidor respondendo na porta 8030 com a nova API e o visualizador. Não há geração
  ou processo de revisão deixado pendente desta rodada.

### Implementação e descobertas

- `niveis.py`: revoicing dentro de uma oitava, redução por nível, escolha de oitavas
  do baixo por programação dinâmica e preenchimento instrumental protegido por voz/palavras.
- Ornamentos do Fácil: regra conservadora só para notas de até 180 ms entre notas iguais,
  sem ataque de palavra. Aplicada antes da quantização em novas gerações; não força toda a escala.
- Armaduras: custo de troca de 12% para 25% do peso típico de um bloco; Médio/Híbrido AMT
  passou de sete a quatro mudanças nas oito músicas, Difícil de sete a cinco.
- **Bug das cifras no MIDI**: `music21` tocava `ChordSymbol` mesmo com `writeAsChord=False`.
  No Acordes–Fácil antigo de No Surprises eram 437 notas escritas e 688 tocadas.
- **Ligações parciais**: exportação direta do Score e `stripTies()` em acordes não eram
  referência suficiente para conferir ligações por nota. Agora `salvar_midi_notas()` lê
  o MusicXML e usa `sincronia.py` para reunir ligações por nota/voz; preserva BPM original.
- `sincronia.py`: interpreta divisions, backup/forward, acordes, pausas, ligações, tempo
  e pautas; atribui IDs às notas. É a fonte comum de tempo para MIDI e visualizador.
- **Não usar o timemap interno do Verovio como relógio**: na validação real houve
  deslocamentos em arquivos com múltiplas vozes/ligações. O SVG preserva IDs explícitos;
  o destaque usa os tempos do MusicXML. Voz zero é renumerada para o importador gráfico.
- **Fontes do Verovio em threads**: definir explicitamente `tk.setResourcePath()` apontando
  ao `data` do pacote em cada toolkit. Sem isso, novos trabalhadores falharam em abrir XML.
- `web/partitura.py` + `GET /api/partitura?arquivo=...`: SVG e mapa em cache por mtime/size
  e versão. A API valida o caminho e serializa a renderização. Cache atual versão 6.
- `web/static/partitura.js`: destaque das notas, cursor no ataque mais recente, busca ao
  clicar, zoom, rolagem automática, descarte ao trocar de versão e botão de tentar novamente.
- **Sincroniza somente a prévia de piano.** O original pausa o piano e limpa o destaque.
  Para sincronizar original, ainda é necessário persistir batidas e origem de cada versão.
- PDF estático mantido em um painel expansível e nos links de download. URLs dos arquivos
  recebem mtime para evitar tocar prévia antiga do cache após regeneração.

### Evidências e reprodução

- Relatório: `ANALISE_PARTITURAS.md`.
- Métricas atuais: `saida/analise_completa.json`, `saida/analise_resumo.json`.
- Backups e métricas antes: `trabalho/revisao_20261109/`, com arquivos originais por música.
  `analise_antes.json` e `resumo_antes.json` nessa pasta foram recalculados pelo analisador novo.
- `analisar_completo.py` analisa a biblioteca; `--antes` analisa os backups. O velho
  `analisar.py`/`saida/analise.json` é histórico e não foi usado para as decisões finais.
- `conferir_previa.py --todas`: **120 MIDIs, 91.401 notas**, alturas/ataques/durações iguais
  ao MusicXML, tolerância de 5 ms para ticks. A análise também contou exatamente 91.401 notas.
- `validar_tempos_visor.py`: IDs e tempos do desenho conferidos em sete partituras,
  incluindo as cinco versões Médias de No Surprises.
- `python -m unittest test_visualizador test_melhorias`: oito testes aprovados.
- `node verificar_visualizador.cjs`: Chrome headless aprovado no desktop/celular,
  reprodução/seek/clique/zoom, pausa entre players e nova recomendação do Difícil.
  Usa Puppeteer já disponível em `C:/Users/mf827/node_modules`; não foi instalada dependência.
- Capturas em `trabalho/visualizador.png` e `visualizador-mobile.png`.
- Scripts de aplicação: `aplicar_melhorias.py`, `revisar_biblioteca.py`, `finalizar_revisao.py`
  e `reparar_previas.py`. Backups são preservados. Não reexecutar regenerações sem necessidade.

### O que continua pendente

Alinhamento forçado da letra oficial e palavras não ouvidas; integração com karaokê;
sincronia com áudio original; avaliação auditiva da fidelidade dos motivos instrumentais.
O alcance foi corrigido, mas isso não elimina erros de transcrição, rubato/síncope ou
trechos ritmicamente difíceis. Não declarar os 100% de concordância com a melodia interna
como acurácia de 100% contra a gravação. Não foi feita revisão humana de todas as páginas.

## 11. Barra contínua durante pausas — 2026-11-10

- Pedido do usuário: a barra desaparecia nas pausas e saltava apenas a cada nota.
- `sincronia.preparar_musicxml(..., com_percurso=True)` agora também retorna intervalos
  dos compassos e âncoras rítmicas de notas/pausas, com IDs explícitos. A chamada padrão
  mantém os dois valores anteriores e não altera a exportação MIDI.
- `web/partitura.py`: cache versão **7**, com `percurso`. Inclui compassos inteiros sem som.
- `partitura.js`: barra interpolada a cada frame pelo relógio do áudio, sem depender
  das notas ativas. Âncoras de notas e pausas seguem o espaçamento musical; pausa de
  compasso inteiro usa limites do compasso, não o símbolo centralizado. A barra muda
  de sistema/página ao atravessar a fronteira e fica no final após o último compasso.
- Geometria recalculada ao mudar zoom/tamanho; destaque das notas continua separado.
  Ao tocar o original, a barra permanece suspensa até voltar à prévia de piano.
- Testes: nove testes Python aprovados; Chrome desktop/celular verifica movimento da
  barra em uma pausa real sem notas ativas, além dos controles anteriores.
- Servidor reiniciado sem pedidos ativos para carregar a mudança. Não foi necessário
  regenerar músicas ou prévias; basta atualizar a página.

## 12. Diagnóstico de três notas em Para Machucar Meu Coração

O usuário indicou Sol♭ em “meu violão”, outro Sol♭ grave em “nosso lar des…” e Lá
natural em “mo-ro-nou”. Verificados MusicXML dos três níveis e duas estimativas
de altura (CREPE/pYIN) em seis trechos da voz isolada, com batidas alinhadas.
Resultados e limites em `DIAGNOSTICO_CORACAO.md`; dados em `trabalho/diagnostico_coracao.json`.
Conclusão: primeiro Sol♭ discretiza uma subida Fá–Sol; o segundo é provável captura
de um ataque grave instável em vez da linha em Ré; Lá natural aparece brevemente
na passagem para Si♭, mas a grade do Médio o alonga. Não trocar Lá por Lá♭ nem
forçar a música inteira à escala. Não foram alterados os arranjos nesta verificação.

## 13. Proteção de ataques/deslizamentos na geração — 2026-11-10

Usuário pediu implementar a proteção no algoritmo. Entregue e aplicada a Para
Machucar Meu Coração nos três níveis, com backup em `trabalho/protecao_20261110/`.

- Novo `protecao_melodia.py`: mede periodicidade, fração de apoio à altura e duração
  do patamar estável por segmento de voz. Remove excursões breves fora do registro
  entre apoios firmes e transições sem patamar que a quantização alongaria.
- Preserva notas longas/cromáticas sustentadas, saltos curtos com apoio forte e
  ataques de palavras apoiados. Não usa escala/acorde como filtro obrigatório.
  Sem diagnóstico de confiança, conserva as notas; não adivinha a correção.
- Regras antes da quantização em Acordes/Híbridos. Médio/Fácil simplificam mais;
  Difícil conserva mais ornamentos. Quando necessário, recupera o início de uma
  palavra na altura firme seguinte, com limite de 250 ms e sem sobrepor notas.
- `melodia(..., diagnostico=...)` mantém retorno antigo (tuplas de três valores),
  adicionando qualidades em um dicionário opcional. `gerar_nivel()` recebe esse
  diagnóstico e registra `[protecao]` no log. CLI/web usam a proteção nas novas gerações.
- Novas execuções do pipeline salvam notas/diagnóstico/batidas/palavras em
  `cache/transcricao.json` e decisões em `cache/protecao_<nivel>.json`.
- Validação real: em Para Machucar, Sol♭ de “violão” (31,33 s, 90 ms), excursão grave
  de “nosso lar” (62,30 s, 160 ms) e passagem de “desmoronou” (22,15 s, 100 ms)
  filtrados no Médio. O Difícil preserva alguns detalhes curtos (ex.: o primeiro Sol♭).
- Foram filtrados 76/71/19 segmentos brutos nos níveis Fácil/Médio/Difícil dessa
  gravação, incluindo outros ataques e transições ao longo da faixa. Isso não é
  uma avaliação humana de que cada trecho removido fosse um erro musical.
- Foram regeneradas as 15 saídas da música; só Acordes/Híbridos usam a proteção
  vocal. Os covers completos continuam com as notas da IA. Reutilizados MIDIs brutos
  das IAs; voz/palavras foram analisadas novamente. As outras sete músicas não foram
  regeneradas nesta rodada e receberão a proteção ao executar o pipeline novamente.
- Snapshot dessa validação em `cache/transcricao_protecao.json`, extração bruta em
  `trabalho/protecao_coracao_bruta.json`; metadata da música marca `protecao_melodia: v1`.
- Utilitários: `avaliar_protecao_coracao.py` (validação sem alterar biblioteca),
  `aplicar_protecao_coracao.py` (reuso da extração e renderização com backup).
- Testes: **19 testes** aprovados. Casos protegem contra apagar cromatismos reais,
  saltos legítimos e ataques de palavras. Auditoria dos 15 MIDIs: **15.249 notas**,
  sem diferenças de altura/ataque/duração em relação ao MusicXML. A API do visor
  carregou a nova versão corretamente; cache é invalidado pelo mtime do MusicXML.
- Métricas da biblioteca recalculadas em `saida/analise_completa.json` e
  `analise_resumo.json`. Mantidas 120 partituras, sem aberturas acima de oitava.
- Servidor não precisou de reinício (gera por subprocesso que lê o código novo).
  Atualizar a página para buscar PDFs/prévias/partitura com novos arquivos.

## 14. Exemplos para o repositório e planejamento da próxima etapa

- Usuário pediu exemplos publicados para comparar, depois pediu um Markdown
  detalhando a próxima etapa. Plano em `PROXIMA_ETAPA.md`, com seis frentes:
  investigação musical, criação de introduções/acompanhamentos, coerência harmônica,
  visualizador, japonês/karaokê e redução de opções apoiada por testes.
- O plano separa métricas objetivas, referências musicais revisadas e preferência
  cega. Propõe benchmark reproduzível antes de escolher novos padrões; não iniciar
  automaticamente todas as implementações só porque estão descritas no documento.
- `exemplos/README.md`: cinco comparações curtas, com SVG/PDF, MP3, MIDI, MusicXML
  e medidas antes/depois. Três trechos de Para Machucar, um de alcance em Garota e
  uma introdução de No Surprises. Total aproximado de 3,4 MB, 58 arquivos.
- Os áudios são novas sínteses dos recortes escritos, com o mesmo piano e andamento;
  não foram incluídos áudios originais, músicas completas, modelos ou caches.
- Recortes preservam contexto e armadura comum nos dois lados. Manifesto registra
  origem relativa, intervalos, medidas e SHA-256. Comparações históricas podem conter
  outras diferenças de transcrição; não são experimento isolado de uma regra.
- Garota ainda mostra texto em inglês indevido; limitação registrada na explicação
  desse exemplo, que avalia apenas alcance. O documento não a apresenta como letra correta.
- `gerar_exemplos.py` reconstrói a seleção a partir da biblioteca/backups locais.
  Os exemplos prontos podem ser usados num clone sem esses arquivos locais.
- `verificar_exemplos.py`: cinco casos, dez pares partitura/MIDI, 205 notas,
  integridade dos arquivos, durações iguais, MP3 audível e SVG com fundo branco.
  Conferência visual de três pares em Chrome realizada. Nenhum modelo foi executado.
- README da Partitura aponta para exemplos/plano; README da raiz agora lista o projeto.

## 15. Mãos tocáveis e dedilhado — 2026-11-10

- Pedido do usuário: partituras mais tocáveis, com a mão calculada (nota ligada precisa
  ser alcançável junto com as próximas) e número dos dedos. Sempre algoritmo, sem LLM.
- Pesquisa: no projeto só havia fechar acorde em uma oitava (`niveis.py`) e escolher a
  oitava do baixo. Fora, o `pianoplayer` (MIT, v3.0.2) dá dedos a partir de MusicXML, mas
  não modela nota segurada nem corrige notas; ficou só como referência.
- Novo `maos.py`: estado = dedo de cada nota que soa no instante; nota segurada mantém o
  dedo. Problemas: `abertura`, `dedos`, `ligada`, `salto`. Correção por janela de ±6
  eventos, aceita só se reduz problemas, escolhendo a menor mudança musical. Até 3 rodadas.
  `separar_maos` impede a esquerda acima da direita (fecha em volta do baixo antes de descer oitava).
- `gerar.py`: `tornar_tocavel` roda por versão depois da transposição do fácil; notas de
  `md_ev` são protegidas. `montar_partitura(..., dedos_md, dedos_me)` grava `<fingering>`;
  continuação ligada de nota dividida no compasso não repete o dedo. CLI: `--dedos`, `--sem-maos`.
- Validação (Linux, venv só com music21/numpy/pretty_midi/verovio, sem GPU): 13 testes novos
  em `test_maos.py` (escalas 1-2-3-1-2-3-4-5, acorde 5-3-1, segurada, salto por nível, melodia
  intocada, mãos sem cruzar) + 19 antigos OK. `avaliar_maos.py exemplos`: Garota antes 8
  trechos difíceis → 0 com 8 correções (7 "fecha o acorde"). Render no Verovio conferido.
  Música sintética de 2200 eventos: ~25 s (memo das digitações por instante, janela
  avaliada uma vez, busca binária na outra mão), esquerda sem problemas restantes.
- Ajustes do dedilhado: redução por tamanho de mão só nos pares com polegar; mesmo dedo
  em outra tecla custa +2; troca de dedo em nota repetida +1,5; mudança de posição custa
  pelo aperto de tempo (pausa longa quase de graça). Referência de método em `test_maos.py`
  (escalas, arpejos, cinco dedos, melodias infantis): 88/97 → **95/97** dedos iguais ao
  livro; a diferença restante (Parabéns 3-2 em vez de 4-3) também é digitação válida.
  Garota: Dó-Dó-Dó-Dó#-Si-Láb-Mi saiu 3-3-3-4-3-2-1.
- Pendente: rodar `avaliar_maos.py saida` e regenerar a biblioteca na máquina Windows;
  ouvir/ler as correções; calibrar o tempo de mudança de posição com quem toca. Harmonia (frente 3
  da PROXIMA_ETAPA) pode reaproveitar o custo da mão pra escolher voicings.

## 16. Letra pelo alinhador do karaokê e partitura de música do karaokê — 2026-11-10

- Pendências 5, 6 e 8 da seção 8. Novo `alinhamento.py`, sem copiar código do karaokê:
  importa `karaoke/server/utils/lrc_pro.align_lyrics_forced` (sys.path no fim da lista).
  Se o `utils.audio` do karaokê não importar (pydub no Python 3.13 pede audioop-lts),
  registra um substituto que carrega o wav com librosa.
- `palavras_alinhadas`: passa as palavras do Whisper já calculadas como `transcribe_fn`
  (estrutura da gravação, sem transcrever de novo) e o LRC do LRCLIB (`buscar_letra(...,
  com_sincronizada=True)`). Verso `fallback` vira buraco preenchido pelo Whisper; palavra
  do Whisper fora de verso é descartada (caso "The girl from Ipanema"). Menos de 50% dos
  versos alinhados: volta pro caminho antigo.
- `--do-karaoke`: mix = vocal.mp3 + backing_track.mp3 (o karaokê apaga o original.mp3
  depois de separar), voz do karaokê, Demucs só no acompanhamento (cópia com o slug no
  nome, senão a pasta do Demucs colide), palavras do segments.json, idioma/título/artista
  do meta.json. `needs_review` com nota < 60 ou poucos versos alinhados: realinha usando o
  lyrics.lrc da música como janela.
- Testes: `test_alinhamento.py` (4) com áudio de zeros e alinhador falso, como os testes do
  karaokê. Suíte inteira: 37 OK (Linux, sem GPU).
- Não validado com modelo: nesta máquina não há GPU nem os áudios do karaokê (só meta.json).
  Na Windows: rodar Garota e Rosa com e sem `--sem-alinhamento` e comparar a letra; rodar
  uma música do karaokê com `--do-karaoke`. O alinhamento usa a GPU fora do lock do servidor
  do karaokê: não rodar durante uma partida.

## 17. Nota pra palavra sem nota — 2026-11-10

- Pendência 2 da seção 8. Antes, sílaba sem nota a mais de 0,8 s sumia e perto grudava
  na nota vizinha (`letra_nas_notas`).
- `melodia()` guarda no diagnóstico os quadros de 10 ms (`quadros`: altura, confiança,
  energia relativa ao volume cantado medido só nos quadros com voz confiante); vão pro
  `cache/transcricao.json`.
- `palavras_sem_nota.notas_para_palavras` roda em `gerar_nivel` depois da proteção da
  melodia. Palavra coberta = nota no ataque (até 150 ms depois do início); 2ª sílaba com
  nota não basta. Exige ≥35% do trecho com voz (> −32 dB do volume cantado); altura =
  mediana dos quadros com confiança ≥ .20; dobra de oitava só se o desvio pras vizinhas
  for ≥ 9 semitons; sem altura, nota seguinte (até 1 s) ou anterior. Cache sem quadros
  (gerações antigas) usa só as vizinhas.
- 8 testes em `test_palavras_sem_nota.py`; suíte 45 OK. Não validado em áudio real:
  conferir "Pensem" (2º/3º verso de Rosa) e se aparece nota onde não se canta.

## 18. Armadura por frase, mínimo de 16 compassos — 2026-11-10

- Pendência 3 da seção 8. Novo `armaduras.py` (o `gerar.armaduras_por_trecho` delega):
  blocos de 4 compassos, cada armadura dura ≥ 16 compassos (ponte de 8 compassos fica
  com acidentes, como nas cifras de Garota), troca no começo de frase da melodia (ataque
  depois de pausa ≥ 1 tempo, até 1 compasso da fronteira do bloco) custa o mesmo que a
  troca antiga e no meio da frase o dobro; a armadura é escrita no compasso da frase.
- Simulação (30 peças por cenário, melodia com 25–50% de notas cromáticas e mão esquerda
  com nota errada em 20–40% dos tempos): modulação Fá→Sol no compasso 37 trocada no
  compasso certo 0/30 (antigo, sempre na fronteira de 8 compassos) → 28–30/30; ponte de
  8 compassos: 3 → 1 troca indevida; peça sem modulação: 0 trocas nos dois.
- `test_armaduras.py` (7). Suíte 52 OK. Conferir na biblioteca: número de trocas por
  música e onde elas caem (Garota Híbrido era o caso ruim).

## 19. Menos acidentes no Fácil — 2026-11-10

- Pendência 1 da seção 8 (~24% das notas da melodia com acidente no Fácil).
  `niveis.alinhar_cromaticas`, só no Fácil, depois de `simplificar_passagens`: nota
  < 1 tempo, fora da escala da armadura da música e fora do acorde detectado naquele
  tempo, que não seja ataque de palavra, vai pro grau vizinho da escala a um semitom
  (prefere nota do acorde, depois repetir a vizinha, depois a mais perto das vizinhas).
  Fica: nota longa, nota do acorde (a sensível do menor é nota do V), ataque de palavra.
  Escala = `escolher_armadura` da melodia + acordes (a mesma conta do Fácil transposto).
  Mudanças em `cache/cromaticas_facil.json`.
- `test_cromaticas.py` (6). Suíte 58 OK. Não medido na biblioteca: rodar
  `analisar_completo.py` antes/depois e conferir a fração de acidentes e a concordância
  da melodia no Fácil. Se cair demais a fidelidade, subir a exigência (ex.: só < 1/2 tempo).

## 20. Partitura acompanhando a gravação original — 2026-11-10

- Pendência da seção 10 ("sincroniza somente a prévia"). `gerar.registrar_sincronia`
  grava `cache/sincronia_original.json` (batidas `bt`/`idx` da grade + `desloc` de cada
  versão, o mesmo de `montar_partitura`, agora em `gerar.deslocamento`).
- `web/partitura.py` (cache versão 8, chave inclui o mtime do arquivo de sincronia)
  devolve `original: {bt, idx, desloc, bpm}`; sem o arquivo (gerações antigas) `None`.
- `partitura.js`: o leitor tem dois relógios (prévia e original) e segue o que está
  tocando; original -> partitura `(interp(t, bt, idx) + desloc) * 60 / bpm` e o inverso
  no clique numa nota. Sem mapa, o original continua limpando o destaque como antes.
- Testado: `test_sincronia_original.py` (renderiza pelo visualizador e confere cada nota
  no segundo do original, gravação com andamento variando) e no Chrome com uma biblioteca
  de teste (original 4,5 s -> nota de 2,0 s; clique -> original 5,40 s; volta pra prévia).
  Suíte 60 OK. Músicas atuais precisam ser regeneradas pra ganhar o mapa.

## 21. Revisão cega e choques melodia × acompanhamento — 2026-11-10

- Página de comparação às cegas em `trabalho/comparacao_20261110/` (gerador `montar.py`
  lá dentro): exemplos com antes/depois/hoje, mesmo piano (TimGM6mb via tinysoundfont),
  partitura sem dedos até revelar, versões de notas iguais agrupadas, "onde muda" por par.
  Usuário julgou: melhoria confirmada depois das técnicas. Achado: o exemplo
  `exemplos/03-desmoronou` publicado tem antes == depois (mesmo MIDI/mp3); refazer o
  recorte na Windows e fazer `verificar_exemplos.py` exigir diferença entre os lados.
- Novo `harmonia.py` (frente 3): `corrigir_qualidade` troca a qualidade do acorde dentro
  da família (maior: maj/7/maj7/6; menor: m/m7/m6) quando a voz sustenta (>= 1 tempo) uma
  nota fora do acorde a um semitom de uma nota dele (C7 + Si cantado -> C7M); família não
  muda (blue note). `tirar_choques` tira do acompanhamento (não o baixo) a voz a um semitom
  da nota cantada forte que soa junto. Tensões sem semitom (9ª, 13ª) ficam.
- `gerar_nivel`: qualidade antes de montar cifras/esquerda; choques por versão antes das
  mãos; registro em `cache/harmonia_<versao>_<nivel>.json`.
- Nos exemplos: só Garota dispara (Dó cantado sobre Sol7M, sai o Si da esquerda nos
  compassos 2-3). `test_harmonia.py` (12). Suíte 72 OK.

## 22. Introdução gerada por teor — 2026-11-10

- Pedido do usuário: introdução sintética (não é a da música), com teor escolhido (animada,
  épica, calma, lenta, emotiva), baseada na música (notas do refrão) e diferente por nível.
  Frente 2 / 4.1 da PROXIMA_ETAPA.
- `introducao.py`: refrão por letra repetida -> desenho melódico repetido -> 1ª frase longa;
  motivo de até 2 compassos alinhado ao compasso (anacruse no lugar) com os acordes
  detectados; teor define textura/registro/aumento/dinâmica; nível define densidade e
  tamanho (4/4/8 compassos); cadência na dominante do 1º acorde da música (emotiva: IV ->
  V com 4ª-3ª). Determinístico; `variacao` troca origem do motivo/registro/arpejo.
- `gerar.com_introducao` põe a introdução nos compassos antes da música (offsets negativos;
  `deslocamento` e a sincronia com o original já tratam: a introdução não tem
  correspondência na gravação). `montar_partitura(..., marcas=)` escreve texto e dinâmica.
  A introdução passa por harmonia/mãos/dedos como o resto (não é protegida).
- CLI `--introducao`, `--variacao`; web: campo "Introdução gerada" (servidor valida).
- `test_introducao.py` (5) com a Ode à Alegria (domínio público). Suíte 77 OK.
  Dinâmica não muda o volume da prévia (MIDI com velocidade fixa) — fica só escrita.
- Avaliação do usuário (página `trabalho/introducoes_20261110/`, Ode à Alegria + trecho de
  Para Machucar): calma/lenta/animada 5 em todos os níveis, emotiva 5 no médio, entrada boa
  em todos; épica 1 (faltam peso e tensão); calma difícil não pode ter figuras curtas na
  esquerda; emotiva difícil rápida demais e parecida com a animada.
- Ajustes: épica com compassos de tensão bVI -> bVII antes da cadência, dominante sus4
  resolvendo na 3ª, esquerda em oitavas graves (no fácil também, como exceção de leitura),
  médio raiz-5ª-oitava em mínimas, difícil oitava + acordes em colcheia; crescendo mp -> f
  -> ff (`info["dinamicas"]`). Calma/lenta: esquerda só com notas >= 2 tempos. Emotiva
  difícil: arpejo em semínimas até a 10ª e iv menor emprestado na cadência. Animada difícil:
  notas destacadas e antecipação do tempo 3.
- Prévia: `salvar_midi_notas` usa a dinâmica escrita como volume (pp 40 ... ff 115; sem
  marca, 90 como antes). Segunda rodada da página em `pagina2/`. Suíte 78 OK.
- 2ª rodada (`pagina2/`): épica (fácil, médio, difícil, Para Machucar), calma, emotiva e
  animada do difícil: todas nota 5 no teor e entrada boa. Todos os 5 teores aprovados nos
  3 níveis. Pendente: validar com músicas inteiras na Windows (refrão de verdade) e, se a
  leitura incomodar, mostrar dedos da introdução difícil só no começo do compasso.

## 23. Final gerado, pedal e fermata — 2026-11-10

- `introducao.gerar_final` (mesmo material do refrão; cadência por teor; acorde final na
  tônica; fácil com acorde final de uma nota e sem passar de Sol5). `gerar.com_final` põe
  no compasso depois da última nota. CLI `--final`, web "Final gerado".
- Marcas novas em `montar_partitura`: "fermata" (nas notas que atacam no offset) e "pedal"
  (PedalMark da 1ª à última nota da esquerda no trecho), aplicadas depois do makeNotation.
  Pedal por acorde em calma/lenta/emotiva (introdução e final). `salvar_midi_notas` grava
  CC64 em todos os canais.
- Tensão da épica: sobe do registro do motivo e para uma oitava acima do centro.
- Página `trabalho/introducoes_20261110/pagina3/` (introdução + começo + final, partitura
  inteira). Suíte 80 OK.
- 3ª rodada (`pagina3/`, introdução + começo + final): 20/20 com nota 5 e final bom.
  Pedido: marcar 8va onde a animada difícil acumula agudos; dedos ao lado da nota (em cima
  ocupava muito espaço).

## 24. 8va e dedos ao lado da nota — 2026-11-10

- `gerar._oitava_acima` (depois do makeNotation): trecho de >= 3 notas da direita, todas
  com a mais grave >= Sol5 e alguma >= Dó6, sem pausa > 2 tempos, é escrito uma oitava
  abaixo com `spanner.Ottava(transposing=False)` — o exportador do music21 erra as oitavas
  com transposing=True. `sincronia.py` passa a ler `octave-shift` (soma a oitava por
  pauta), então MIDI da prévia e visualizador tocam/destacam na altura real.
- `gerar.dedos_ao_lado(svg)`: Verovio só põe dedilhado em cima/embaixo; com a opção
  `svgAdditionalAttribute: fing@startid` cada número sabe a nota, e o pós-processamento
  leva o número pra esquerda da cabeça (antes do acidente), `fingeringScale` 0.6. Perto de
  clave/armadura/fórmula de compasso fica em cima. Aplicado no PDF, no visualizador
  (cache versão 9) e nas páginas de comparação.
- Testes em `test_maos.py` (8va e dedos). Suíte 82 OK.- Achado na conferência: cifra que cai no meio de uma nota da direita fazia o music21
  criar uma 2ª voz só de pausas (pausas soltas embaixo das notas). Cifras agora entram
  depois do makeNotation, direto no compasso. Vale pra todas as partituras.- Pedal: o "Ped. *" sobrepunha o asterisco de soltar e o Ped. seguinte a cada troca.
  Agora é linha de pedal (colchete), um por acorde, terminando na nota que abre o trecho
  seguinte: os colchetes encadeados viram a linha com entalhe em cada troca. O `change`
  do MusicXML não é desenhado pelo Verovio (só o 1º colchete aparece), por isso o encadeamento.
  A prévia solta o pedal na troca (`PedalMark.fim_q`), não no fim da nota seguinte.- Linha de pedal batia nas cifras do sistema de baixo (o Verovio não conta o pedal na
  colisão; `spacingSystem` padrão 4). Agora 12 em todo desenho (PDF, visualizador v10, páginas).- Os colchetes encadeados ainda se cruzavam na troca ("||"). O `bounce` do MEI também não
  é desenhado pelo Verovio (testado: só o 1º colchete aparece). Solução: `gerar.pedal_continuo`
  pós-processa o SVG, juntando por sistema os colchetes encostados numa linha só com
  gancho no começo/fim e entalhe "^" em cada troca. PDF, visualizador (v11) e páginas.- Dedos na 1ª nota do sistema (colada em clave/armadura/compasso) ficavam em cima; agora
  vão pra direita da cabeça se não baterem em nota, acidente ou barra (largura da cabeça
  pelo glifo SMuFL), e só com os dois lados ocupados ficam em cima.

## 25. Anotado: experimento com separação em 6 faixas

- Usuário sugeriu o Moseca; o útil é o `htdemucs_6s` (guitarra e piano separados), que já
  está no `demucs`. Hipóteses, protocolo e critério de decisão em `PROXIMA_ETAPA.md` §12.
  Nada implementado; teste na Windows.

## 26. Trava nos exemplos, --reusar-cache e "Outra variação" — 2026-11-10

- `gerar_exemplos.py` recusa recorte com antes == depois; `verificar_exemplos.py` reprova
  (hoje reprova o 03-desmoronou de propósito; README dos exemplos avisa).
- `gerar.py --reusar-cache`: usa `cache/transcricao.json` (se for do mesmo áudio: tamanho
  e mtime) e só escreve as partituras; pula Demucs, batidas, melodia, acordes e letra.
  Testado de ponta a ponta aqui com a Ode (cache montado à mão): harmonia, mãos, intro
  épica, final calmo, PDF e prévias.
- Web: `POST /api/variacao {pasta}` copia PDFs/prévias/editáveis pra `variacoes/v<N>/`,
  gera a variação N+1 com `--reusar-cache` e os mesmos níveis/versões; `/api/musicas`
  devolve introducao/final/variacao/variacoes; botão "Outra variação" no visor. Testado
  com o servidor local (job pronto, v0 guardada, meta com variação 1).
- Notado: a cifra G7 do compasso 23 da Ode saiu perto da pauta de baixo (compasso só com
  pausas na direita); ver depois.

## 27. Métricas pesquisadas e 6 faixas pronto pra testar — 2026-11-10

- `METRICAS_VALIDACAO.md`: pesquisa (subagente, web) de métricas sem LLM pra validar as
  partituras, priorizadas: Qmax/DTW da prévia × original, MCA e F1 via mir_eval, tensão do
  spiral array (pacote partitura), descritores de dificuldade do RubricNet, dissonância
  sensorial, 2º modelo de dedilhado, ritmo (LHL, RGC/IPE, groove), MGEval.
- `gerar.py --separador htdemucs_6s` + `gerar.harmonia_das_faixas`; `experimento_6faixas.py`
  com testes das contas (`test_experimento_6faixas.py`). Rodar na Windows (PROXIMA_ETAPA §12).

## 28. Validação da biblioteca num comando — 2026-11-10

- `metricas.py`: fidelidade (Qmax de recorrência cruzada + desvio do DTW, prévia × original,
  cortando introdução/final), melodia (MCA e F1 via mir_eval contra a voz do cache),
  dificuldade por mão (descritores do RubricNet, só no corpo da música), grave embolado
  (low interval limits), groove da esquerda, tensão do spiral array se `partitura` instalado.
- `comparacao_cega.py`: página às cegas antes × depois com trechos reais (alinha os lados
  pela melodia cantada, acha os 4 compassos que mais mudaram, recorta, desenha sem dedos,
  toca com o piano das prévias).
- `validar_biblioteca.py`: antes (cópia + métricas) → regenerar (mesmos níveis/versões;
  `--rapido` usa o cache; argumentos depois de `--` vão pro gerar.py) → depois →
  relatorio.md (média por versão/nível e quebra de monotonia fácil<médio<difícil) → página.
  Testado de ponta a ponta aqui com a Ode. `test_metricas.py`. Suíte 90 OK.
- Achado: a correção das mãos (fechar o acorde pra caber) aumenta o grave embolado
  (terças abaixo de Dó3) na versão Acordes; na Ode, difícil 40/min com correção × 9/min sem.
  Próximo passo: fechar o acorde num registro acima do limite, com teste às cegas.

## 29. Acompanhamento da música inteira no teor — 2026-11-10

- `acompanhamento.py`: esquerda da versão Acordes com as texturas da introdução por teor,
  sobre os acordes detectados; compasso com canto denso usa a textura um nível abaixo;
  pedal por acorde em calma/lenta/emotiva; dinâmica da música = a do teor.
  `--acompanhamento <teor>`; web "Acompanhamento (versão Acordes)". Híbridos não mudam.
- Página `trabalho/acompanhamento_20261110/pagina/` (Ode, médio e difícil, 5 teores +
  padrão de hoje). `test_acompanhamento.py`. Suíte 93 OK.

## 30. Japonês: letra em moras — 2026-11-10

- `japones.py`: pronúncia como se canta (fugashi do karaokê; senão pykakasi), corte em
  moras (kana pequeno, ー e っ juntam com a anterior; ん própria), romaji ou kana.
  `letra.silabas(..., "ja")` usa isso; `gerar.py --escrita-ja romaji|kana`.
- Romaji ok no desenho. Kana: sem hífen, mas o Verovio mede o texto como latino e os kana
  ficam espremidos (pendente: espaçamento/fonte CJK). Kana mostra a pronúncia (とー), não a
  grafia (とう). Falta testar com música japonesa real (Whisper "ja" + alinhamento).
- `test_japones.py`. Suíte 96 OK.


## 31. Sessão Windows: grave claro, fácil fiel, Híbrido Gravado, música inteira — 2026-11-10 (noite)

- `validar_biblioteca.py` acha o áudio das músicas sem `cache/transcricao.json` e tem `--so`.
  Biblioteca regenerada; revisão cega da música inteira: novo ganhou 8×4; recado "o fácil não
  parece a música"; Híbrido AMT no médio "muito melhor"; Baby com desvio do DTW 5,4 → 24,5 s.
- `maos.clarear_grave` (grave embolado 35,7/min → 0 no Acordes médio), kana espaçado, cifra em
  compasso de pausa; `--facil-fiel`; `--gravado` (`gravado.py`); `comparacao_completa.py`.
- Exemplo 03 refeito; `--do-karaoke` testado (Águas de Março); experimento 6 faixas sem referências.

## 32. Melodia reconhecível — 2026-11-10 (noite)

- `afinacao.py`: desvio de afinação da voz descontado antes de arredondar; nota fora da escala e
  do acorde vai pro grau vizinho quando a altura puxava pra ele ou é curta (Don't Look Back in
  Anger 179/590 fora do tom; biblioteca 20–40% → 0–4%). `--melodia-crua` desliga.
- Prévia com a melodia em destaque (`gerar.DESTAQUE`, só volume). `reparar_previas.py` voltou a funcionar.
- Nota repetida colada sem sílaba vira sustentada (20–34% dos ataques da direita eram repetição);
  `--juntar-silabas`, `--repetidas` volta ao antigo.
- `limpeza.py`: melodia no topo, bordadura falsa A-B-A, repetidas da esquerda viram nota segurada.
- `metricas.py`: fora do tom, repetidas e melodia no topo no relatório (guarda contra regressão).

## 33. Níveis derivados do médio — 2026-11-10 (noite)

- `derivados.py` (proposta do usuário), padrão desde então (`--sem-derivar` volta): fácil =
  melodia do médio + uma nota grave por acorde; difícil = 3ª/6ª embaixo das longas, oitava nos
  picos, arpejo no lugar de bloco/repetidas, pedal por acorde, fermata. Só tríade nos acréscimos.
- Aba Karaokê no site (`/api/karaoke`, `/api/gerar_karaoke`), capa pelo vídeo de origem do karaokê.

## 34. AMT-APC como base, modo leve e front novo — 2026-11-11 (madrugada)

- Escuta do usuário: AMT-APC é a melhor versão, até que o Híbrido. `--versoes` escreve só o
  pedido; prévias no fim, 8 em paralelo, ganho no lugar do loudnorm (Rosa de Hiroshima do cache
  ~2 min → 11 s). Site mostra só o AMT-APC nos 3 níveis.
- `--leve` (`gerar_nivel_leve`): sem Demucs/CREPE/Whisper; batidas e acordes da mistura, tempo 1
  pelas notas graves do AMT-APC (`fase_pelo_midi`). Rosa do zero em CPU (Windows) 87 s. **Sem letra.**
- `corrigir_fase`: o baixo forte no 1 e no 3 deixava a fase meio compasso deslocada em ~metade
  das músicas; se as trocas de acorde caem claramente mais no 3, anda 2 batidas.
- `tonalidade.py`: tom por trecho (Krumhansl-Kessler + Viterbi), vocabulário da música, função
  melódica; só o erro provável do AMT-APC muda (348 notas na biblioteca). `--tom-ia-cru` desliga.
- Front refeito do zero: um campo que filtra a biblioteca e busca no YouTube com Enter, Gerar num
  toque com progresso no cartão, música em tela cheia com Fácil/Médio/Difícil, partitura que
  acompanha, barra de controle. Trem das Onze do clique até pronta: 31 s. README: montar num servidor.

## 35. AMT-APC no Linux e armadura de Águas de Março — 2026-11-11

- Diretriz do usuário: **AMT-APC é a base de tudo**; o resto são ferramentas determinísticas pra
  deixar o arranjo mais tocável e legível.
- AMT-APC instalado no Linux (CPU, torch 2.x CPU). torchaudio >= 2.9 pede torchcodec pra ler
  áudio: o lançador do `amtapc.py` cai pro soundfile quando ele falta. Águas de Março (3:34)
  do zero em 8 min neste notebook (8 núcleos); do cache, 31 s.
- Achado (usuário: "diversos bemóis"): armadura de Mi♭ (−3) numa música em Si♭ (Krumhansl 0,91
  × 0,48). `custo_por_armadura` só contava nota fora da escala e o Lá♭ do Si♭7 (mixolídio) pesava
  mais que o Lá. Agora `armaduras.custo_do_histograma` soma a distância do tom provável
  (`PESO_TONICA` 0,5, perfis do `tonalidade.py`), por bloco no DP.
- Grafia da cifra: raiz sempre bemol em tom com bemóis gerava Lá♭dim7 (Sol𝄫, Mi𝄫) e F#7 com Lá#.
  `gerar.acorde_com_grafia` escolhe a grafia da raiz com menos acidentes contra a armadura, sem
  dobrado. Águas de Março médio: 22 dobrados → 0, acidentes 189 → 161 (fácil 117 → 103,
  difícil 340 → 291). Os que sobram são a harmonia (Lá♭ do Si♭7, Sol♭ do Mi♭m6, Mi♮ do Dó7).
  Antes/depois em `trabalho/bemois_20261111/`. Testes em `test_armaduras.py`. Suíte 127 OK.

## 36. Tocabilidade por regra no modo leve — 2026-11-11

- `tocavel.py`: `medir` (ataques por tempo, notas juntas, síncopes que atravessam o tempo, saltos
  da esquerda > oitava em < 1 tempo, mudanças de posição/min e trechos difíceis do `maos.py`) e
  `ajustar` por nível: `desfazer_sincopes` (antecipação vai pro tempo e a nota anterior segura;
  não mexe se atropela outro ataque ou se a nota fica < 1/2 tempo), fácil nas duas mãos e médio só
  na esquerda; `oitavas_da_esquerda` (DP com oitava −12/0/+12 por ataque, custo do deslocamento
  além de 7 semitons dividido pelo tempo disponível, +3 por mudar, proibido sair da faixa ou
  encostar na direita), fácil e médio (no difícil a esquerda é arpejo). Difícil não muda.
- `gerar.montar_partitura`: nota cromática fora do acorde com grafia pela direção (sobe #, desce ♭).
- Águas de Março (144 bpm): fácil síncopes da direita 94 → 0, mudanças da esquerda 2,6 → 1,4/min;
  médio síncopes da esquerda 105 → 7, mudanças 9,2 → 5,7/min, acidentes 161 → 155. Densidade já
  baixa (1,25 ataque/tempo; a grade do nível segura), sem regra nova. `--sem-ajuste` desliga.
- Medição: `trabalho/tocavel_20261111/medir.py <pasta>`. `test_tocavel.py`. Suíte 136 OK.
- Pedido do usuário ouvindo a página: tirar o nome dos acordes de cima da partitura ("atrapalha").
  `gerar.MOSTRAR_CIFRAS = False` (só não desenha; a grafia continua pelo acorde), `--cifras` volta.
  Visualizador `VERSAO` 13. Suíte 137 OK.
- Página 1 (Águas, Ode, fácil e médio): aprovada ("ficou muito bom com a mudança"). Pedido:
  testar outros gêneros. Fuyu no Hanashi (J-pop, 136 bpm), Anna Júlia (rock, 152 bpm), Cálice
  (MPB) geradas no Linux; armaduras conferidas contra Krumhansl nas 5 músicas (todas batem:
  Si♭, Lá♭, Fá, Mi♭, Mi).
- Fuyu: atrasar a antecipação criou 2 trechos difíceis (salto de 11 semitons ficou com 0,44 s).
  `desfazer_sincopes` não move quando o salto pra próxima nota passa de uma quinta e o tempo que
  sobra é menor que base + distância/velocidade do `maos.PERFIL` do nível. Fácil, síncopes da
  direita antes → depois: Águas 94 → 15, Ode 88 → 7, Fuyu 100 → 26, Anna Júlia 56 → 5, Cálice
  75 → 13, sem trecho difícil novo. Médio, esquerda: 105 → 17, 66 → 14, 40 → 12, 46 → 8, 58 → 2.
- Pegadinha: `while read ... done <<EOF` com `python`/`yt-dlp` dentro: o processo lê o stdin e
  engole as linhas seguintes da lista; passar `</dev/null`. Suíte 138 OK.
- Página 2 aprovada: "as músicas são iguais, mas a partitura ficou bem mais legível". O ajuste
  fica como padrão do modo leve (`--sem-ajuste` desliga).

## 37. 8va desenhada duas oitavas abaixo e 8va por linhas suplementares — 2026-11-11

- Usuário (Fuyu no Hanashi médio): "qual a lógica de mandar uma oitava acima e colocar as notas lá
  embaixo? escrever lá embaixo é tão ruim quanto lá em cima". Causa: o `_oitava_acima` escrevia a
  nota uma oitava abaixo e o Verovio, que lê a altura do MusicXML como a que soa, baixava de novo
  (MEI `oct` 4, `oct.ges` 5 pra um Dó6). A pegadinha antiga ("transposing=True exporta oitavas
  erradas") era diagnóstico errado. Agora a altura fica a que soa e o `sincronia.py` não soma
  oitava. `test_oitava.py` confere pelo MEI do Verovio. Visualizador `VERSAO` 14.
- Regra nova: DP nas notas da direita (normal × 8va), custo = linhas suplementares desenhadas +
  6 por linha 8va nova (metade depois de pausa longa), nota embaixo da pauta dentro da 8va ×100.
  5 músicas × 3 níveis: linhas 8va 79 → 62, suplementares em cima 828 → 624, nenhuma nota embaixo
  da pauta dentro da 8va. Varredura (abrir/peso): 4/1 62·487·45 embaixo; 8/4 38·723·12; 12/4 29·810·12.
- Difícil: a direita muda de posição 35–50/min contra 15–19 no médio. Experimento: sem a 3ª/6ª
  embaixo das notas longas cai pra 24–35; sem a oitava dos picos nada muda; acrescentar a 3ª/6ª só
  em nota sozinha, só com abertura ≤ 7/9 ou conduzindo a voz interna (peso 0,5–2) não muda nada.
  É o próprio tocar em terças; fica. Chaves do experimento desfeitas no `derivados.py`.
- Suíte 143 OK.

## 38. Rodada 3: dedo, oitava do fácil, graves pra esquerda, atraso das batidas — 2026-11-11

- Direção do usuário: modo leve é o padrão; letra não cabe nele (precisa de Demucs + tempos);
  quer um leve otimizado, legível, fácil e condizente com a música.
- Dedo dentro da nota (acorde com segunda: a cabeça vizinha fica do outro lado da haste e o dedo
  "à esquerda" caía em cima dela). `dedos_ao_lado` confere cabeças/acidentes/barras/começo do
  sistema também à esquerda; ocupado, passa pra esquerda da vizinha; senão direita; senão em cima.
- Fácil na oitava confortável: oitava única pra música toda não serve (Fuyu fácil vai de Dó4 a
  Sol6; descer criou 224 linhas suplementares embaixo). `tocavel.oitava_por_frase`: DP por frase
  (pausa >= 1 tempo ou 16 tempos na barra), custo = linhas suplementares (ou a frase sob 8va, se
  melhor) + 3 por frase mudada + salto > oitava entre frases; só aceita se `custo_leitura` (a mesma
  DP da 8va do gerar, linhas + 6 por 8va) cair. Fuyu fácil: custo 144 → 104 (8va 14 → 3 antes dos
  passos seguintes; na partitura final 12 → 2 linhas 8va, suplementares 33 → 61); Águas 113 → 104.
- Graves da direita pra esquerda (`graves_pra_esquerda`): nota abaixo de Ré4 que não é a de cima vai
  pra esquerda se ela está livre ou ataca junto com a mesma duração e o acorde cabe na mão do nível
  (`maos.PERFIL` abertura, até 4 notas). Pouco efeito (0–4 notas por partitura): nos graves de
  Cálice (96 linhas embaixo no difícil) é a própria melodia que desce, e ela não sai da direita.
- Atraso das batidas: os ataques do AMT-APC caem 34–39 ms antes da batida detectada nas 5
  músicas (mediana até o tempo/meio tempo mais próximo). Deslocar a grade piorou: Anna Júlia médio
  síncopes 38 → 47, suplementares 25 → 35; Fuyu difícil 112 → 159. Descartado; a batida do áudio fica.
- Suíte 154 OK.
- Página às cegas do fácil aprovada: "ficou muito boa a simplificação".
- Dois dedos na mesma nota (imagem do usuário): a primeira versão da correção do dedo conferia
  qualquer cabeça à esquerda; em grau conjunto o dedo ia pra direita e caía no dedo da nota
  seguinte (15 partituras: 1 → 232 sobreposições). Agora: regra antiga + só a cabeça do mesmo
  acorde colada à esquerda (segunda, até 0,6 espaço, sem contar o próprio acidente), reservando o
  lugar do dedo dela a partir do acidente dela; e cada dedo posto ao lado é guardado, outro não
  pode cair em cima (distância vertical < 0,7 da fonte: terça empilha, segunda não). Resultado:
  0 sobreposições, 16 dedos em cima da nota (eram 15). Conferência:
  `trabalho/rodada3_20261111/dedos_sobrepostos.py`.

## 39. Velocidade do AMT-APC em CPU, clave da direita e repetições — 2026-11-11

- AMT-APC em CPU (trecho de 60 s de Águas de Março, notebook com load alto): 86 s; o modelo é
  ~10 s por segmento de 512 quadros (linear 40%, atenção 20%, softmax 8%); espectro e notas < 0,2 s.
  8 threads (núcleos lógicos): −10%, notas idênticas → no lançador do `amtapc.py`. Quantização int8
  dinâmica nas lineares: −15 a −22%, mas 425 × 377 notas (F1 0,85 contra o original) → fora (mudaria
  o arranjo base). `inference_mode`: nada.
- Clave de fá na direita por DP (compasso a compasso, troca na barra): não disparou em nenhuma das
  15 partituras e foi removida. O AMT-APC já separa as mãos em Dó4; as "linhas embaixo" contadas
  eram quase todas o Dó central (1 linha suplementar, leitura normal). Só o difícil põe nota abaixo
  (3ª/6ª até Sol3: 13 em Cálice).
- Repetições: quase nenhum compasso se repete igual (Ode fácil 14/99, Águas 1/125), nem bloco de 4
  compassos; pela melodia (Levenshtein por bloco de 4) só Ode e Anna Júlia têm blocos ≥ 70% iguais.
  O mesmo trecho sai transcrito diferente a cada vez. Unificar as repetições (achar as seções com
  alinhamento livre e escrever igual) seria o próximo passo grande pra leitura e estudo; muda o
  conteúdo, precisa de página às cegas.

## 40. Repetições escritas iguais (consenso) — 2026-11-11

- Pedido do usuário: identificar as repetições e dar o mesmo padrão de notas (facilita aprender).
- Pesquisa (o que já existe): consenso entre repetições na transcrição de letra (McVicar, Ellis e
  Goto, ICASSP 2014), modelo da própria peça pras repetições no ritmo (Nakamura et al., arXiv
  1908.06969), refinamento por segmentos repetidos em música folclórica (AES), autossimilaridade
  pra métrica na transcrição de piano (Shibata, Nakamura e Yoshii, arXiv 2008.12710), Etude (piano
  cover com etapa de estrutura, arXiv 2509.16522). Nenhum força consistência num arranjo pronto.
- Detecção pelas notas por compasso só achou a Ode. Pelo áudio, cromagrama cru casa tudo com tudo;
  receita padrão (croma sem a média, 8 batidas empilhadas, recorrência kNN, `path_enhance`) achou
  a estrutura: Ode e Anna Júlia a cada 16 batidas, Águas 64–80, Cálice ~32–35 (rubato), Fuyu 154
  (= 38,5 compassos: repetição deslocada meio compasso, métrica a corrigir; Shibata et al.).
- `repeticoes.py`: lags do áudio (picos, múltiplos de compasso, >= 4 compassos) → confirmação pelas
  notas (impressão de classes de altura por meio compasso, cada mão normalizada à parte, cosseno
  >= 0,6 por 4+ compassos) → grupos por união-busca, apertados (cosseno >= 0,75 contra o medoide;
  sem isso a Ode encadeava 87 de 99 compassos em 6 grupos) → consenso por votação (ataque a 1/4 de
  tempo + altura presentes na maioria; vazio → medoide). No médio do modo leve antes de derivar;
  `--sem-repeticoes` desliga.
- Compassos iguais a um anterior (fácil): Ode 14 → 49/99, Anna Júlia 15 → 47/131, Águas 1 → 6,
  Fuyu 3 → 6, Cálice 1 → 4. Página às cegas `trabalho/rodada4_20261111/pagina`. `test_repeticoes.py`.
  Suíte 158 OK.

## 41. Robustez, regressão automática e repetições sem piora — 2026-11-11

- Usuário: "ouvir ficou igual, provavelmente só tocando pra saber"; pediu commit (73f0d4d), mais
  robustez e pesquisa mais funda ("música é matemática").
- Robustez: modo leve de ponta a ponta num trecho de 60 s quebrava em `acordes` (cromagrama geral
  e do grave com 1 quadro de diferença; agora cortados no menor). `test_robustez.py` com entradas
  vazias/degeneradas; a análise de repetição pelo áudio falhando não derruba a geração.
- `regressao.py`: mede as partituras prontas (linhas suplementares com a 8va como o Verovio desenha,
  nota embaixo da pauta na 8va, linhas 8va, acidentes, trechos difíceis, mudanças de posição,
  síncopes, compassos repetidos, dedos sobrepostos no SVG, ordem fácil < médio < difícil), salva
  referência (`--salvar`) e acusa piora (`--base`, sai com 1). 15 partituras em ~45 s.
- A regressão pegou o consenso piorando a tocabilidade: voto nota a nota montava acordes que
  nenhuma versão tinha (Fuyu médio, trechos difíceis 1 → 7); voto por acorde ainda montava
  sequências inexistentes (saltos dentro do compasso) e replicava enfeite agudo (Ode difícil, notas
  acima de Lá5 52 → 100). Final: o padrão do grupo é uma versão REAL inteira, a que mais concorda
  com a votação menos 2 × linhas suplementares (`PESO_LEITURA`, varredura 0,5–4: 2 é o único sem
  piora de leitura), e compasso cuja emenda obriga a direita a um salto sem tempo (maos.PERFIL)
  fica como estava. Contra antes das repetições: única piora acusada é síncope no difícil de Anna
  Júlia (134 → 149; no difícil a síncope é mantida de propósito).
- Pesquisa (subagente, citações conferidas): top 5 pra CPU — (1) downbeat/compasso: madmom DBN com
  beats_per_bar=[2,3,4] (Böck, Krebs e Widmer, ISMIR 2016) + fase por trecho pelas estatísticas
  de Shibata, Nakamura e Yoshii (2021) + alinhamento das repetições (caso Fuyu); (2) grafia ps13
  (Meredith 2006, 99,3%; `partitura.musicanalysis.estimate_spelling`); (3) seções por spectral
  clustering (McFee e Ellis, ISMIR 2014; librosa) pra ritornelo/casa 1-2; (4) métricas automáticas
  (Score Analyzer, Sébastien et al. ISMIR 2012; MV2H, McLeod e Steedman ISMIR 2018); (5) dedilhado
  por HMM (Nakamura, Saito e Yoshii 2020) e redução com dificuldade controlada (Nakamura e Yoshii,
  APSIPA 2018). Suíte 161 OK.

## 42. Batidas e tempo 1 pelo madmom no modo leve — 2026-11-11

- madmom 0.17.dev0 (GitHub; o PyPI 0.16 não compila em Python 3.13), RNN + DBN de downbeat (Böck,
  Krebs e Widmer, ISMIR 2016), `beats_per_bar=[3, 4]`: ~36 s de CPU por música.
- As 5 músicas saíram 4/4 constante: o "compasso de 2 tempos" de Fuyu não existe; a grade do librosa
  ganhava 13 batidas (478 × 465) e a repetição caía em 38,5 compassos. As batidas do madmom vêm
  ~40 ms antes das do librosa, o mesmo atraso medido nos ataques do AMT-APC (§38).
- Medidas objetivas, librosa + fase heurística → madmom: ataques do arranjo no tempo Águas 38 → 55%,
  Anna Júlia 51 → 63%; grave no tempo 1 Ode 16 → 38% (a heurística errava a fase em 2 tempos: troca
  de acorde não separa o 1 do 3), Cálice 26 → 45%; repetições em compasso inteiro Fuyu 0/3 → 2/3.
- `gerar.batidas_madmom` no modo leve (sem madmom ou `--batidas-librosa`: grade antiga; com ele, a
  fase vem do madmom e `fase_pelo_midi`/`corrigir_fase` não rodam). Compasso de 3 detectado só avisa:
  a partitura ainda é 4/4 em todo o código (pendência: 3/4 e 6/8 de verdade).
- Regressão (soma das 15 partituras): síncopes 1092 → 834, compassos repetidos 298 → 423, linhas
  suplementares 832 → 739, linhas 8va 49 → 37, mudanças de posição 501 → 470/min; acidentes 1472 →
  1517, trechos difíceis 17 → 20 (vêm da grade, não das repetições: testado com --sem-repeticoes).
- Dedo que fica em cima da nota agora entra na lista dos já postos e sobe se bater em outro
  (Cálice fácil tinha 1 sobreposto). Suíte 161 OK; referência da regressão atualizada.
