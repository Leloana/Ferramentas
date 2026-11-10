# 🎹 Partitura — música com vocal → partitura de piano

Pega uma música normal (com voz e banda) e gera **PDF + MusicXML + MIDI** de piano, mais uma prévia `.mp3` sintetizada pra ouvir sem software.

Veja os [exemplos de antes/depois](exemplos/README.md) e o [plano da próxima etapa](PROXIMA_ETAPA.md).

## Interface web

```powershell
cd partitura
.\venv\Scripts\python.exe run.py          # http://127.0.0.1:8030  (--lan pra abrir na rede)
```

Busca a música no YouTube (com prévia ▶), escolhe dificuldade e versões, acompanha a fila
e abre a partitura na biblioteca (PDF, prévia ao piano, gravação original, MusicXML).

## Níveis de dificuldade (`--nivel facil,medio,dificil` ou `todos`)

| | Fácil | Médio | Difícil |
|---|---|---|---|
| Ritmo | semínima | colcheia | semicolcheia |
| Mão esquerda (Acordes) | só o baixo, segurado | baixo + 3ª e 7ª | baixo + acorde em ritmo |
| Pop2Piano / Híbrido | 1 nota por mão | até 2–3 notas | completo |
| Cifra | tríades | completa | completa |
| Tom | armadura única, transposto pra sem acidentes | original | original |

Arquivos: `<Versão> - <Nível>.pdf` (ex.: `Hibrido - Facil.pdf`).

## Rodar pela linha de comando

```powershell
cd partitura
.\venv\Scripts\python.exe gerar.py entrada\musica.wav --titulo "Nome" --subtitulo "Autor" [--letra letra.txt] [--pop2piano] [--hibrido] [--nivel todos] [--idioma auto] [--sem-letra]
```

Tudo automático, sem LLM: só modelos de áudio (Demucs, torchcrepe, Whisper, Pop2Piano) + regras musicais.

Saída organizada por música (`--idioma en` pra letra em inglês):

```
saida/<Título>/
  Original.mp3  áudio de origem
  Acordes.pdf   Acordes - previa.mp3
  Hibrido.pdf   Hibrido - previa.mp3
  Pop2Piano.pdf Pop2Piano - previa.mp3
  editaveis/    .musicxml (abre no MuseScore pra corrigir à mão) e .mid
  cache/        MIDI bruto do Pop2Piano
```

## Duas versões

| | `gerar.py` (padrão) | `--pop2piano` |
|---|---|---|
| Mão direita | melodia **cantada** (voz isolada pelo Demucs → torchcrepe) | melodia + enfeites do modelo |
| Mão esquerda | acordes detectados em bloco (fundamental + 3ª + 7ª) a cada 2 tempos | acompanhamento "de pianista" gerado |
| Bom pra | lead sheet / tocar e cantar | arranjo pra tocar solo |

`--hibrido` junta o melhor das duas: **melodia cantada com letra** na mão direita + **acompanhamento do Pop2Piano** na esquerda (`<nome>_hibrido.pdf`). O MIDI do Pop2Piano fica em cache (`saida/<nome>_pop2piano_bruto.mid`).

As três usam a mesma grade de batidas e a mesma cifra. Gerar as três: `--pop2piano --hibrido`.

## Estilos do Pop2Piano (`--estilo 1-21`)

O Pop2Piano imita 21 pianistas ("composer1..21"). Medido em Baby (Justin Bieber):

| estilo | notas/s | notas por ataque | % notas graves | leitura |
|---|---|---|---|---|
| 1 (padrão) | 6,1 | 1,56 | 19% | mão esquerda fraca |
| 4 | 6,4 | 1,62 | 40% | equilibrado |
| 8 | 7,8 | 2,40 | 27% | muitos acordes (difícil) |
| 12 | 6,7 | 1,64 | 48% | mais baixo |
| 21 | 5,7 | 1,50 | 39% | mais leve |

Amostras em `saida/Baby/estilos_pop2piano/`.

## AMT-APC (`--amtapc`)

IA de "piano cover" de 2024 ([310hz/amt-apc](https://github.com/310hz/amt-apc), artigo arXiv 2409.14086),
4ª versão ao lado do Pop2Piano. Instalação em `modelos/amt-apc` (ver `amtapc.py`). Roda em ~7 s por música
na RTX 4070 (Pop2Piano: ~30 s). Seus estilos `level1/2/3` são ligados aos níveis, mas **não são dificuldade de
verdade** (o level1 gera até mais notas que o Pop2Piano), então passa pela mesma simplificação por nível.

## Versão recomendada por nível

Revisão de **120 partituras, oito músicas**, com relatório completo em [ANALISE_PARTITURAS.md](ANALISE_PARTITURAS.md).

| Nível | Principal | Notas/s direita / esquerda | Abertura > oitava |
|---|---|---:|---:|
| Fácil | **Acordes** | 1,25 / 0,57 | 0% |
| Médio | **Híbrido AMT** | 2,09 / 1,48 | 0% |
| Difícil | **Híbrido AMT** | 2,58 / 1,41 | 0% |

O Híbrido mantém melodia e letra e agora aproveita a direita da IA nos trechos instrumentais.
AMT-APC completo continua como alternativa de cover instrumental, sem letra. A redução fecha acordes
e escolhe oitavas do baixo para diminuir saltos. As oito músicas foram atualizadas; os backups ficam
em `trabalho/revisao_20261109/`. Alcance menor não garante ritmo fácil nem transcrição exata.

`python analisar_completo.py` gera as métricas em `saida/analise_completa.json` e `analise_resumo.json`.
`python conferir_previa.py --todas` confere alturas, ataques e durações dos MIDIs contra o MusicXML.
O analisador antigo `analisar.py` e `saida/analise.json` são históricos; as métricas atuais usam ligações
por nota e alinhamento temporal entre as versões.

### Proteção da melodia vocal

Novas gerações de Acordes e Híbridos analisam confiança, estabilidade e duração de
cada nota antes de quantizar. Filtram quedas breves fora do registro e deslizamentos
que virariam notas longas na grade, preservando cromatismos sustentados e ataques
de palavras apoiados. O Difícil conserva mais ornamentos. A regra não força notas à escala.

O motivo de cada remoção fica em `cache/protecao_<nivel>.json`; a extração com
diagnóstico fica em `cache/transcricao.json`. Em 2026-11-10, Para Machucar Meu Coração
foi regenerada para validar os exemplos indicados pelo usuário; os arquivos anteriores
estão em `trabalho/protecao_20261110/`. As outras músicas receberão a proteção quando regeneradas.

### Mãos tocáveis e dedilhado

Antes de montar a partitura, `maos.py` confere cada mão ao longo do tempo com um
modelo da mão: limite de abertura entre cada par de dedos (tabela de Parncutt/Jacobs,
escalada por nível), nota segurada prendendo a mão no lugar, número de dedos livres e
tempo pra mudar a mão de posição. Uma programação dinâmica acha a melhor digitação.
Nada de LLM nem modelo treinado.

Quando nenhuma digitação cabe, só o acompanhamento muda, na ordem de menor mudança
musical: fecha o acorde, muda a oitava, solta a nota segurada e, por último, tira uma
nota. A melodia cantada nunca muda; trecho difícil dela fica só registrado. A esquerda
também não sobe por cima da direita.

| | fácil | médio | difícil |
|---|---|---|---|
| maior abertura da mão | oitava | oitava | 9ª menor |
| tempo pra mudar a mão de lugar (oitava) | ~0,85 s | ~0,5 s | ~0,3 s |
| números dos dedos | todas as notas | só onde a mão muda de posição | só onde a mão muda de posição |

`--dedos todos|mudancas|nenhum` troca o padrão; `--sem-maos` só calcula os dedos, sem
corrigir notas. O que foi corrigido e o que ficou difícil vai pra `cache/maos_<versao>_<nivel>.json`.
`python avaliar_maos.py saida` mede partituras já geradas sem regenerar nada.

## Partitura acompanhando o áudio

Na Biblioteca, a **prévia de piano** destaca as notas em um visualizador SVG com cursor,
rolagem automática e zoom. A barra avança continuamente pelo tempo de cada compasso,
inclusive nas pausas e notas sustentadas. Clique numa nota para ir até aquele momento. Desmarque
**Acompanhar piano** para rolar livremente. O PDF estático continua disponível abaixo e para download.

Ao tocar a gravação original, o piano pausa e o destaque é limpo. A sincronia com o original
ainda não está implementada. O visualizador e o MIDI usam os mesmos tempos do MusicXML;
cifras não são tocadas como notas extras. O servidor guarda o desenho e os tempos em cache
e os recalcula quando o MusicXML muda.

## Etapas

1. **Demucs** (`htdemucs`) separa voz / baixo / bateria / resto (cache em `trabalho/`).
2. **Batidas** (librosa) seguindo o pulso real (rubato de gravação ao vivo), tempo 1 pelo baixo.
3. **Melodia**: torchcrepe + filtro de volume, histerese de 40 ms contra vibrato, notas repetidas divididas por ataque.
4. **Acordes**: chroma do "resto + baixo", 9 tipos (maj, m, 7, 7M, m7, m7(b5), °, 6, m6), Viterbi pra não piscar.
5. **Armadura por trecho** (blocos de 8 compassos, custo pra trocar) — ex.: Chega de Saudade sai Ré menor → maior.
6. **Letra** (`letra.py`): Whisper `large-v3-turbo` marca o tempo de cada palavra na voz isolada (sem VAD, que corta canto; filtra alucinações tipo "Música"/CAIXA ALTA), `--letra` corrige a grafia pela letra oficial, pyphen separa sílabas e um alinhamento global (programação dinâmica) põe uma sílaba por nota, em ordem.
7. **Grafia** das notas guiada pelo acorde ativo (A7 = A C♯ E G).
8. **music21** → MusicXML/MIDI; **Verovio** → SVG; Chrome headless → PDF.

## Prévia com piano de verdade

As prévias `.mp3` são tocadas pelo **FluidSynth** com um SoundFont de piano de cauda (Steinway NY Model B,
"Dore Mark's NY S&S Model B v5.2", da coleção soundfonts4u). Ambos ficam fora do git:

- `ferramentas/fluidsynth/.../bin/fluidsynth.exe` — release oficial win10-x64 do GitHub (FluidSynth/fluidsynth)
- `soundfonts/piano.sf2` — https://huggingface.co/datasets/projectlosangeles/soundfonts4u

Sem eles, cai num sintetizador simples (senoides).

## Limites conhecidos

Na interface, o seletor **Estilo do Pop2Piano** oferece os 21 estilos quando Pop2Piano ou Híbrido
está marcado. O padrão continua sendo o estilo 1. A escolha também afeta o acompanhamento do
Híbrido (Pop2Piano); Acordes e as versões AMT não usam esse estilo. Na linha de comando: `--estilo 1` a `--estilo 21`.

- Precisa ter **voz** na faixa: em gravação instrumental a melodia está na orquestra e a versão padrão não acha nada (use `--pop2piano`).
- Ritmo é o ponto fraco: síncope e rubato (bossa!) saem aproximados. O nível Médio usa colcheias; o Difícil, semicolcheias.
- A letra aparece em Acordes e nos Híbridos. Os covers completos não recebem letra. Palavra que o Whisper não ouviu (ex.: primeira do verso) continua faltando.
- O tempo 1 do compasso é um chute pelo baixo; a cifra às vezes erra tensões.
- `essentia` não tem build pra Windows: `_stubs/essentia` é um substituto que só entrega as batidas pro Pop2Piano do `transformers`.
