# 🎹 Partitura — música com vocal → partitura de piano

Pega uma música normal (com voz e banda) e gera **PDF + MusicXML + MIDI** de piano, mais uma prévia `.mp3` sintetizada pra ouvir sem software.

Documentação: [estado atual, pendências e pegadinhas](HANDOFF.md) ·
[plano por frentes](PROXIMA_ETAPA.md) · [métricas de validação](METRICAS_VALIDACAO.md) ·
[histórico das sessões](HISTORICO.md) · [exemplos de antes/depois](exemplos/README.md).

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
.\venv\Scripts\python.exe gerar.py entrada\musica.wav --titulo "Nome" --artista "Artista" `
    --nivel todos --hibrido --amtapc --idioma auto
```

Tudo automático, sem LLM: modelos de áudio (Demucs, torchcrepe, Whisper, MMS_FA, Pop2Piano,
AMT-APC) + regras musicais. Opções principais:

| opção | o que faz |
|---|---|
| `--nivel facil,medio,dificil` / `todos` | níveis gerados |
| `--hibrido`, `--pop2piano`, `--amtapc`, `--estilo 1-21` | versões com acompanhamento de IA |
| `--idioma pt\|en\|ja\|auto`, `--letra arq.txt`, `--sem-letra`, `--sem-busca-letra`, `--sem-alinhamento` | letra |
| `--escrita-ja romaji\|kana` | japonês embaixo das notas (uma mora por nota) |
| `--introducao <teor>`, `--final <teor>`, `--variacao N` | introdução/final gerados (calma, lenta, emotiva, animada, epica) |
| `--acompanhamento <teor>` | esquerda da música inteira no teor (versão Acordes) |
| `--dedos auto\|todos\|mudancas\|nenhum`, `--sem-maos` | números dos dedos; desligar a correção das mãos |
| `--sem-transpor` | fácil sem transpor pra tom sem acidentes |
| `--separador htdemucs\|htdemucs_6s` | separação em 4 ou 6 faixas (guitarra e piano) |
| `--do-karaoke <música>` | entrada vinda do karaokê (voz, acompanhamento e letra já prontos) |
| `--reusar-cache` | só reescreve as partituras a partir de `cache/transcricao.json` |

Saída por música em `saida/<Título>/`:

```
Original.mp3                       áudio de origem
<Versão> - <Nível>.pdf             ex.: "HibridoAMT - Medio.pdf"
<Versão> - <Nível> - previa.mp3    como a partitura soa (piano de cauda; dinâmica e pedal)
editaveis/                         .musicxml (MuseScore) e .mid
cache/                             transcrição, MIDIs brutos das IAs e o registro de cada etapa
variacoes/vN/                      variações anteriores de introdução/final
meta.json                          vídeo, título, artista, teores escolhidos
```

### Letra alinhada e músicas do karaokê

Com letra oficial (LRCLIB ou `--letra`), depois do Whisper a partitura usa o alinhador
forçado do karaokê (`../karaoke/server/utils/lrc_pro.py`, MMS_FA): cada palavra da letra
oficial vai pro tempo em que é cantada na voz separada, verso a verso pelo LRC sincronizado,
e a estrutura da gravação (verso pulado ou repetido ao vivo) sai das palavras do Whisper.
Verso que o alinhador não acha fica com as palavras do Whisper; palavra do Whisper fora de
qualquer verso (alucinação na introdução) não entra. Com menos da metade dos versos
alinhados, fica tudo como antes (Whisper + correção de grafia). `--sem-alinhamento` desliga.
O resultado vai em `cache/transcricao.json` (`origem_letra`, `alinhamento`).

```powershell
.\venv\Scripts\python.exe gerar.py --do-karaoke a-flor-los-hermanos --nivel todos --hibrido --amtapc
```

`--do-karaoke` (slug de `../karaoke/server/songs` ou caminho da pasta) usa a voz e o
acompanhamento que o karaokê já separou (o Demucs roda só no acompanhamento, pro baixo e a
bateria) e as palavras do `segments.json`. Letra marcada pra revisão no karaokê (nota < 60)
é alinhada de novo. Precisa de `Unidecode`, `RapidFuzz` e `Metaphone` (requirements).

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

### Palavra sem nota

Quando o detector de melodia não pega o ataque de uma palavra (começo de verso soprado,
como o "Pensem" de Rosa de Hiroshima), `palavras_sem_nota.py` cria a nota antes da
quantização: só se houver voz de verdade naquele trecho (senão é alucinação da
transcrição), com a altura dos quadros do detector aceitando confiança menor, trazida
pra oitava das vizinhas quando o desvio é de oitava; sem altura confiável, a da nota
seguinte. Nunca sobrepõe nota existente. Criadas e recusadas em `cache/palavras_sem_nota_<nivel>.json`.

### Introdução gerada (`--introducao calma|lenta|emotiva|animada|epica`)

Acrescenta antes da música uma introdução que **não existe na gravação**: feita do refrão
(frase cuja letra mais se repete; sem letra, o desenho melódico que mais se repete), com
os acordes dele, na textura do teor escolhido (calma: acordes abertos sustentados; lenta:
motivo com durações dobradas; emotiva: arpejo e apojatura na cadência; animada: baixo e
acorde alternados, registro mais agudo; épica: baixo em oitavas, acordes em bloco, motivo
dobrado). Fácil: uma nota por mão, 4 compassos; médio: padrões simples, 4 compassos;
difícil: arpejos e dobramentos, 8 compassos. Termina na dominante do primeiro acorde da
música. A partitura marca "Introdução gerada (teor)" e "Música". `--variacao N` dá outra
versão controlada (origem do motivo, registro, sentido do arpejo). Parâmetros em
`cache/introducao_<nivel>.json`. Na interface: campo "Introdução gerada" no pedido.

### Final gerado (`--final calma|lenta|emotiva|animada|epica`) e pedal

Final que não existe na gravação, depois da última nota: fácil/médio 2 compassos (cadência
com o contorno do refrão preso às notas dos acordes + acorde final), difícil 4 (2 de motivo
do refrão). Cadência por teor: calma IV -> I (plagal), lenta IV -> iv -> I, emotiva iv -> I,
animada IV -> V7 -> I com dois golpes no fim, épica bVI -> bVII -> I em ff. Termina na
tônica (o 1º acorde da música), com fermata (menos na animada) e "rit." nos teores calmos.
Calma, lenta e emotiva levam pedal trocando a cada acorde, na introdução e no final; a
prévia toca o pedal (CC64) e as dinâmicas escritas.

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

Os números ficam **ao lado** da nota (à esquerda, antes do acidente; à direita quando a
esquerda está ocupada por clave/armadura/compasso; em cima só sem lugar), menores que o
padrão do Verovio. Trechos agudos da direita saem em **8va**.

`--dedos todos|mudancas|nenhum` troca o padrão; `--sem-maos` só calcula os dedos, sem
corrigir notas. O que foi corrigido e o que ficou difícil vai pra `cache/maos_<versao>_<nivel>.json`.
`python avaliar_maos.py saida` mede partituras já geradas sem regenerar nada.

## Partitura acompanhando o áudio

Na Biblioteca, a **prévia de piano** destaca as notas em um visualizador SVG com cursor,
rolagem automática e zoom. A barra avança continuamente pelo tempo de cada compasso,
inclusive nas pausas e notas sustentadas. Clique numa nota para ir até aquele momento. Desmarque
**Acompanhar piano** para rolar livremente. O PDF estático continua disponível abaixo e para download.

Ao tocar a gravação original, o piano pausa e a partitura passa a seguir a gravação, pelas
batidas detectadas (`cache/sincronia_original.json`); clicar numa nota leva a gravação até ela.
Músicas geradas antes disso não têm esse mapa: nelas o destaque é limpo. O visualizador e o MIDI usam os mesmos tempos do MusicXML;
cifras não são tocadas como notas extras. O servidor guarda o desenho e os tempos em cache
e os recalcula quando o MusicXML muda.

## Etapas

1. **Separação** (Demucs `htdemucs`, ou `htdemucs_6s` com guitarra e piano), cache em `trabalho/`.
2. **Batidas** (librosa) seguindo o pulso real, tempo 1 pelo baixo.
3. **Melodia**: torchcrepe + filtro de volume, histerese contra vibrato, proteção contra
   ataques instáveis (`protecao_melodia.py`), nota pra palavra sem nota (`palavras_sem_nota.py`).
4. **Acordes**: croma + Viterbi, 9 tipos; qualidade corrigida pela voz sustentada (`harmonia.py`).
5. **Letra**: Whisper + alinhamento forçado da letra oficial pelo karaokê (`alinhamento.py`),
   sílabas por pyphen (japonês: moras, `japones.py`), uma sílaba por nota por programação dinâmica.
6. **Níveis** (`niveis.py`): grade rítmica, esquerda, cromatismos curtos do fácil levados à escala.
7. **Introdução/final/acompanhamento** gerados por teor (`introducao.py`, `acompanhamento.py`).
8. **Tocabilidade** (`maos.py`): dedilhado por programação dinâmica, correção do acompanhamento
   que a mão não alcança, voz do acompanhamento em semitom com a voz tirada (`harmonia.py`).
9. **Partitura**: armadura por frase (`armaduras.py`), grafia pelo acorde, 8va nos agudos,
   dedos ao lado da nota, pedal em linha, fermata; music21 → MusicXML/MIDI; Verovio → SVG;
   Chrome → PDF.

## Validação

`validar_biblioteca.py` mede a biblioteca antes, regenera, mede depois e monta um relatório e
uma página às cegas com trechos reais (ver `METRICAS_VALIDACAO.md`): fidelidade da prévia à
gravação (Qmax, DTW), melodia contra a voz (MCA e F1 via mir_eval), dificuldade por mão
(fácil < médio < difícil), grave embolado, padrão rítmico da esquerda. `avaliar_maos.py`
mede só os trechos difíceis pra mão; `experimento_6faixas.py` compara 4 × 6 faixas.

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
- A letra aparece em Acordes e nos Híbridos. Os covers completos não recebem letra.
- O tempo 1 do compasso é um chute pelo baixo; a cifra às vezes erra tensões.
- A esquerda fechada pra caber na mão pode embolar no grave (terças abaixo de Dó3); em estudo.
- Japonês em kana fica espremido no desenho; use romaji (padrão).
- `essentia` não tem build pra Windows: `_stubs/essentia` é um substituto que só entrega as batidas pro Pop2Piano do `transformers`.
