# Handoff — Partitura (sessão de 2026-11-09)

**Estado atualizado até a seção 14.** As seções 6 e 7 registram a análise anterior à revisão das 120 partituras.

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

