# Partida de teste: Rap do Gaara (Player Tauz), cantada pelo Lelo

Gravação real de 2026-10-01 (celular Android como microfone, TV como tela), para depurar a
nota em qualquer PC sem precisar cantar. Só a voz do cantor: o instrumental e a voz da música
não estão aqui.

| Arquivo | O que é |
| :--- | :--- |
| `Lelo.wav` | voz do celular, 16 kHz mono, no tempo da música (silêncio onde não chegou pacote) |
| `session.json` | partida inteira (formato 3): versos com tempos, o que o Whisper ouviu em cada verso (com e sem dica), nota por verso, eventos, versões e constantes do servidor |
| `gabarito.json` | anotação do cantor, verso a verso: 53 "certo", 13 "errado" |
| `song_lyrics.lrc`, `song_meta.json`, `song_pitch.json` | cópia da música no dia (letra revisada à mão: `song_lyrics_edited`) |

## Rodar

```powershell
cd karaoke
# rápido, sem GPU: repontua as palavras gravadas com o score atual
.\venv\Scripts\python.exe -m pytest tests/replay -q -s

# completo: Whisper de novo no WAV, como no jogo (~1 min na GPU)
$env:KARAOKE_REPLAY = "1"; .\venv\Scripts\python.exe -m pytest tests/replay -q -s

# tabela verso a verso (gravada × nova × gabarito), trocando constantes
.\venv\Scripts\python.exe tools/replay_recording.py tests/fixtures/replay/rap-do-gaara-lelo
.\venv\Scripts\python.exe tools/replay_recording.py tests/fixtures/replay/rap-do-gaara-lelo --set mic_stream.FAST_VERSE_TAIL_SEC=0
```

## Referência (2026-10-02, commit 702ed83, `large-v3-turbo` na RTX 4070)

- Repontuar as palavras gravadas: nota 87,7, erro médio contra o gabarito 12,3.
- Replay com Whisper: nota 88,4, erro 11,5 (sem a folga do verso rápido: 87,2 / 12,7).
- O Whisper varia ±1–2 pontos entre rodadas e entre GPUs; CPU (int8) dá números um pouco diferentes.

É rap (~12 letras/s): exercita a folga do verso rápido (`mic_stream.FAST_VERSE_TAIL_SEC`), a voz
de apoio entre parênteses ("Eu sou (eu sou)") e a remoção de vazamento entre versos.
