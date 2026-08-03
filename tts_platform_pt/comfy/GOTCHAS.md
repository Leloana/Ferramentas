# Gotchas do pipeline de geração de imagens (ComfyUI / Krea2 turbo)

Leia isto antes de mexer em `scripts/gerar_imagens.py`, `scripts/montar_video.py`
ou no workflow `image_krea2_turbo_t2i.json`. São achados de depuração real,
não teoria — cada um custou uma rodada (ou várias) de geração pra isolar.
Datado: descoberto rodando o projeto `Projetos/video-curto/humanidade*`.

## 1. Nudez em figuras humanas — guarda-corpo tem que estar no prompt, não no workflow

O `krea2_turbo` desenha gente nua por padrão quando o prompt não menciona
vestimenta, mesmo com o system prompt do refino (node `30:18`) já tendo uma
regra 8 ("assuma roupa cobrindo anatomia íntima"). Essa regra sozinha **não
funciona** porque a regra 5 do mesmo system prompt manda o refino não
inventar detalhe de vestuário que o input não sustenta — as duas regras se
cancelam quando o input não fala de roupa.

- **Não funcionou**: desconectar o node `ConditioningKrea2Rebalance` da
  saída positiva do `KSampler`. Parecia um parâmetro de "descensura" à
  primeira vista — só reduziu o quão explícita a nudez saía, não eliminou.
- **Funcionou**: declarar vestimenta explicitamente no próprio prompt de
  entrada (`_SUFIXO_SEGURANCA` em `gerar_imagens.py`). Isso aciona a regra
  1 do system prompt (preservar o que o input já diz) em vez de esbarrar
  na regra 5.
- Mesmo com o guarda-corpo, trate a saída como rascunho — revise as
  imagens antes de usar no vídeo final.

## 2. Texto borrado desenhado por cima da cena — a causa raiz não é sorte de seed

Sintoma: a imagem sai com letras garranchadas sobrepostas à cena,
frequentemente ecoando (mal escrita) a própria frase de entrada — às vezes
até o nosso `_SUFIXO_SEGURANCA` aparece garranchado no meio do "texto".

**Causa raiz**: o node de refino (`TextGenerate`, `30:16`) tem sua própria
regra 4 no system prompt ("se o usuário pedir texto visível, coloque entre
aspas"). Pra frases de narração que soam como uma citação fechada (tom
declarativo, termina em ponto), o refino decide sozinho que aquilo é
"texto pra mostrar na tela" e cita a frase como legenda. O modelo de
difusão então tenta desenhar essas letras — e diffusion models são
notoriamente ruins nisso, daí o garrancho.

**Por que "regenerar com seed novo" sozinho NÃO resolve**: o node
`TextGenerate` tem `sampling_mode.seed` **fixo em `0`** no workflow. Só
randomizamos o seed do `KSampler` (a difusão). Pra uma mesma frase de
entrada, o refino sempre produz a mesma descrição — e o mesmo defeito, não
importa quantas vezes troquemos o seed da difusão. **Testado
explicitamente**: regenerei 6 imagens quebradas só com seed novo do
`KSampler`; só 1 saiu corrigida. As outras 5 repetiram o mesmo tipo de
defeito.

**O que ajudou parcialmente**: encurtar `_SUFIXO_SEGURANCA` de uma frase
inteira ("todas as pessoas retratadas devem estar completamente vestidas
com roupas apropriadas ao contexto e à época da cena, sem nudez") pra um
fragmento curto tipo tag (", com roupas apropriadas, sem nudez"). Corrigiu
algumas frases, não todas.

**O que resolveu de fato**: apensar uma regra extra ao system prompt do
refino, só na cópia do workflow que a gente envia por request (variável
`_REGRA_SEM_TEXTO` em `gerar_imagens.py`, **não** mexe no
`image_krea2_turbo_t2i.json` salvo), proibindo explicitamente renderizar o
input (ou paráfrase/citação dele) como texto visível. Depois dessa regra,
todas as frases que ainda estavam quebradas saíram limpas.

**Se esse defeito voltar a aparecer**: primeiro suspeite de frases muito
"citáveis" (tom declarativo, frases de efeito, negações abstratas tipo "não
éramos a espécie mais forte" — hipótese: sentenças difíceis de visualizar
diretamente fazem o refino recorrer a mostrar o texto como saída "segura").
Regenerar com seed novo sozinho não é diagnóstico confiável de que está
corrigido — sempre confira visualmente.

## 3. Formato vertical (9:16) é bem menos confiável que 16:9 nesse modelo

Gerando as 9 frases de um teste direto em `9:16 (Portrait Widescreen)`
(antes da correção do item 2), **6 de 9 imagens saíram com defeito**: 4
rotacionadas 90° (cena inteira de lado, como se a câmera tivesse virado),
1 tríptico (3 painéis empilhados da mesma cena em vez de uma imagem só), 1
com texto borrado. Isso é uma taxa de defeito bem mais alta do que a
observada gerando em 16:9 (só nudez, sem rotação/tríptico/texto).

Depois da correção do item 2 (regra extra contra texto visível), a rotação
e o tríptico também pararam de aparecer nas regenerações — então é
possível que os três sintomas tenham uma raiz comum (o refino "confuso"
tentando encaixar uma descrição num formato que não domina tão bem). Mas
não isolei uma causa definitiva pra rotação/tríptico como isolei pra texto
— se voltar a acontecer, considere voltar a gerar em 16:9 e recortar
(pan/crop) pro vertical no ffmpeg, que é o caminho mais testado/confiável
historicamente neste projeto.

## 4. Zoom tremendo no vídeo final — supersample antes do `zoompan`

Sintoma: o efeito de zoom em `montar_video.py` (`renderizar_clipe_imagem`)
tremia visivelmente em vez de deslizar suave.

**Causa**: as imagens do ComfyUI nascem perto do tamanho final (768x1368
pra uma saída de 1080x1920). O filtro `zoompan` recalcula a janela de
corte em **pixels inteiros** a cada frame; numa imagem só um pouco maior
que a saída, esse arredondamento é uma fração grande do deslocamento entre
frames — o zoom "pula" em vez de deslizar.

**Fix** (técnica padrão, bem documentada, não é invenção deste projeto):
escalar a imagem pra bem maior que a saída final ANTES do `zoompan`
(`_SUPERSAMPLE = 4` em `montar_video.py`, ou seja ~4320x7680 pra uma saída
de 1080x1920), deixando o parâmetro `s=` do próprio `zoompan` reamostrar
pra baixo no final. O mesmo arredondamento de pixel inteiro vira uma fração
desprezível numa imagem 4x maior.

**Não dá pra validar "tremor" olhando frames extraídos isolados** — é um
efeito de movimento, só aparece reproduzindo o vídeo de verdade. Ao mexer
nisso, confirme rodando o vídeo, não só inspecionando stills.

## 5. Metodologia: teste filtros do ffmpeg isolados antes de integrar

Vários dos gotchas acima (este arquivo e os do `CLAUDE.md` sobre
`original_size` do filtro `subtitles`) só ficaram claros isolando o filtro
problemático numa cadeia sintética mínima (`ffmpeg -f lavfi -i color=...`)
e comparando variações uma de cada vez, em vez de tentar depurar dentro do
pipeline completo. Um filtro do ffmpeg pode "aceitar" uma opção sem erro
nenhum no log (`-loglevel verbose` confirma a opção sendo lida) e mesmo
assim produzir um resultado completamente errado — silenciosamente. Não
confie em "rodou sem erro" como sinal de "saiu certo" pra filtro de vídeo;
sempre confira visualmente (frame extraído pra coisas estáticas tipo
posição/tamanho de legenda, vídeo reproduzido de verdade pra coisas de
movimento tipo zoom/pan).

## 6. Timing de geração é instável (60s a 362s por imagem)

Não isolei a causa raiz. Confirmado que não é disputa de VRAM com o
XTTS-v2 (checar processos com `nvidia-smi
--query-compute-apps=pid,process_name,used_memory --format=csv` durante
uma geração lenta — só o `python.exe` do ComfyUI aparecia como processo de
cômputo). Reiniciar o ComfyUI Desktop no meio de uma sessão de testes
pareceu "curar" períodos de lentidão nas poucas vezes que testei, mas não
confirmei causalidade — pode ter sido coincidência. Cancelar o script no
meio de uma geração não aborta automaticamente o job que já estava
`queue_running` no ComfyUI; `POST /interrupt` ajuda mas não é imediato se
o job estiver preso no `TextGenerate` (LLM), que parece não checar
cancelamento tão granularmente quanto o `KSampler`.
