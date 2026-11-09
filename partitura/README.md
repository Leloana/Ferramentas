# 🎹 Partitura — música com vocal → partitura de piano

Pega uma música normal (com voz e banda) e gera **PDF + MusicXML + MIDI** de piano, mais uma prévia `.mp3` sintetizada pra ouvir sem software.

## Rodar

```powershell
cd partitura
.\venv\Scripts\python.exe gerar.py entrada\musica.wav --titulo "Nome" --subtitulo "Autor" [--pop2piano] [--grade 4]
```

Saída em `saida/`. O MusicXML abre no MuseScore pra corrigir à mão.

## Duas versões

| | `gerar.py` (padrão) | `--pop2piano` |
|---|---|---|
| Mão direita | melodia **cantada** (voz isolada pelo Demucs → torchcrepe) | melodia + enfeites do modelo |
| Mão esquerda | acordes detectados em bloco (fundamental + 3ª + 7ª) a cada 2 tempos | acompanhamento "de pianista" gerado |
| Bom pra | lead sheet / tocar e cantar | arranjo pra tocar solo |

As duas usam a mesma grade de batidas e a mesma cifra.

## Etapas

1. **Demucs** (`htdemucs`) separa voz / baixo / bateria / resto (cache em `trabalho/`).
2. **Batidas** (librosa) seguindo o pulso real (rubato de gravação ao vivo), tempo 1 pelo baixo.
3. **Melodia**: torchcrepe + filtro de volume, histerese de 40 ms contra vibrato, notas repetidas divididas por ataque.
4. **Acordes**: chroma do "resto + baixo", 9 tipos (maj, m, 7, 7M, m7, m7(b5), °, 6, m6), Viterbi pra não piscar.
5. **Armadura por trecho** (blocos de 8 compassos, custo pra trocar) — ex.: Chega de Saudade sai Ré menor → maior.
6. **Grafia** das notas guiada pelo acorde ativo (A7 = A C♯ E G).
7. **music21** → MusicXML/MIDI; **Verovio** → SVG; Chrome headless → PDF.

## Limites conhecidos

- Precisa ter **voz** na faixa: em gravação instrumental a melodia está na orquestra e a versão padrão não acha nada (use `--pop2piano`).
- Ritmo é o ponto fraco: síncope e rubato (bossa!) saem aproximados. `--grade 2` (colcheia, padrão) é mais legível; `--grade 4` é mais fiel e mais poluído.
- O tempo 1 do compasso é um chute pelo baixo; a cifra às vezes erra tensões.
- `essentia` não tem build pra Windows: `_stubs/essentia` é um substituto que só entrega as batidas pro Pop2Piano do `transformers`.
