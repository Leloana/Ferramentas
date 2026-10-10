# Estado da produção — Guerra do Paraguai (Video_15)

Parado em 2026-10-10, ~00:30, a pedido do usuário. Retomar daqui.

## Feito
- `texto.md` (292 palavras), `descricao.md`, `vozes.md` (ElevenLabs, voz David).
- Áudio: `audio/texto.wav` (131s, 28 frases, tempos por palavra) + `texto_manifesto.json`. Não precisa regerar.
- `texto_prompts.json` com as 28 cenas.
- Imagens revisadas e boas: 1-7, 9-11, 13, 14, 16, 18, 20-22, 24-27.

## Falta
1. Regerar as frases **8, 12, 15, 17, 19, 23, 28** com `--sem-refino`:
   - 8 saiu girada 90° (gotcha 3); as outras ainda não tinham sido regeradas sem o refino.
   - Com o refino ligado, 15 de 28 saíram com texto garranchado ou como anime (GOTCHAS item 20).
2. Revisar as imagens novas.
3. `montar_video.py`.
4. `gerar_capa.py` com `--prompt` escrito à mão (o refino também roda ali).

## Comandos (a partir de tts_platform_pt/)
```powershell
# ComfyUI: o app "Comfy Desktop" fecha sozinho ao abrir (2026-10-10), e o "ComfyUI" antigo
# está com base_path quebrado. Subir o backend direto:
cd $env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI; .\.venv\Scripts\python.exe -s main.py --port 8188
# imagens que faltam
.\venv\Scripts\python.exe scripts\gerar_imagens.py Projetos\Video_15\guerra_do_paraguai_1864\texto_manifesto.json --prompts Projetos\Video_15\guerra_do_paraguai_1864\texto_prompts.json --sem-refino --frases 8,12,15,17,19,23,28
# montagem e capa
.\venv\Scripts\python.exe scripts\montar_video.py Projetos\Video_15\guerra_do_paraguai_1864\texto_manifesto.json
.\venv\Scripts\python.exe scripts\gerar_capa.py Projetos\Video_15\guerra_do_paraguai_1864\texto_manifesto.json --prompt "..."
```
O servidor TTS (porta 8011) não é necessário pra terminar, porque o áudio já está pronto.
