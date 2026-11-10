# Handoff — Partitura (sessão de 2026-11-09)

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

**Padrão por nível** (definido pela análise, seção 6): **Fácil = Acordes · Médio = Híbrido (AMT) · Difícil = AMT-APC**.
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
4. **Escolha de estilo do Pop2Piano na interface** (hoje só `--estilo` na linha de comando); usuário ainda não
   escolheu um estilo padrão.
5. **Alinhamento forçado da letra oficial** (como o karaokê faz com MMS_FA) em vez de Whisper + correção:
   resolveria trechos perdidos nas bossas.
6. **Integração com o karaokê**: gerar partitura direto das músicas da biblioteca (stems e letra alinhada já existem).
7. Rap/trap (Bandido com Bandida): melodia é aproximada (voz meio falada) — esperado.
8. "The girl from Ipanema" alucinado no início de Garota (não é caixa alta, passa no filtro).
