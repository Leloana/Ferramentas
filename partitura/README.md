# 🎹 Partitura — música com vocal → partitura de piano

Pega uma música normal (com voz e banda) e gera **PDF + MusicXML + MIDI** de piano, mais uma prévia `.mp3` sintetizada pra ouvir sem software.

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

- Precisa ter **voz** na faixa: em gravação instrumental a melodia está na orquestra e a versão padrão não acha nada (use `--pop2piano`).
- Ritmo é o ponto fraco: síncope e rubato (bossa!) saem aproximados. `--grade 2` (colcheia, padrão) é mais legível; `--grade 4` é mais fiel e mais poluído.
- A letra vai só na versão melodia + acordes (no Pop2Piano a melodia não é a cantada). Palavra que o Whisper não ouviu (ex.: primeira do verso) fica faltando.
- O tempo 1 do compasso é um chute pelo baixo; a cifra às vezes erra tensões.
- `essentia` não tem build pra Windows: `_stubs/essentia` é um substituto que só entrega as batidas pro Pop2Piano do `transformers`.
