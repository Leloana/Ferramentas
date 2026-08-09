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

## 7. Prompt bilíngue (seed em inglês + sufixo em português) engasga o refino

Sintoma: a imagem sai com um bloco de texto garranchado colado por cima ou
abaixo da cena, ecoando fragmentos das PRÓPRIAS regras que a gente apensa
ao system prompt do refino — variações de "Step 1: ... roupas
apropriadas, sem ..." / "Step 2: No On-Screen Text ...". Não é o bug do
item 2 (a narração sendo citada) — aqui o texto garranchado vem das minhas
regras extras (`_REGRA_SEM_TEXTO`, `_REGRA_PROMPT_CURTO`, `_SUFIXO_SEGURANCA`),
não da frase do usuário.

**Causa provável**: depois que `--prompts` passou a existir em
`gerar_imagens.py`, o seed enviado pro refino virou bilíngue — a descrição
reescrita à mão em inglês + `_SUFIXO_SEGURANCA` ainda em português
(", com roupas apropriadas, sem nudez") grudado no fim da mesma string.
Esse code-switching no meio de um prompt só apareceu depois de introduzir
`--prompts`; antes disso o seed inteiro (frase da narração) era sempre
português, sem mistura. O `qwen3vl_4b` (modelo pequeno, 4B) parece
"engasgar" com prompts bilíngues às vezes, produzindo uma saída que mistura
fragmentos das regras do próprio system prompt em vez de uma descrição
visual limpa — e o texto degenerado então é desenhado na cena pelo
`KSampler`.

**Correção aplicada**: traduzir `_SUFIXO_SEGURANCA` pro inglês
(`", fully clothed, appropriate attire, no nudity"`) — mesmo idioma do
seed que `--prompts` usa. Reduziu bastante a taxa de defeito, mas **não
eliminou**: numa auditoria de 39 imagens (4 partes) depois da correção,
ainda apareceu 1 caso novo na mesma frase que já tinha quebrado antes da
correção (ver item abaixo sobre reescrever o prompt).

**Regenerar com o mesmo prompt pode resolver, mas não é garantido**: numa
imagem, regenerar (mesmo prompt, seed novo do `KSampler`) corrigiu de
primeira. Noutra (frase sobre "areia virando microchip", frase que usava
"transitioning into"), o mesmo prompt quebrou **3 vezes seguidas** —
reescrever o prompt (tirar a construção "X transitioning into Y", ir direto
pra uma descrição de cena estática) corrigiu na primeira tentativa depois
disso. Ou seja: se uma frase quebrar 2x seguidas com o mesmo prompt,
pare de tentar seed novo e reescreva o texto do prompt — há frases/
construções que parecem ser gatilho confiável, não apenas azar de
amostragem.

## 8. O modelo pode ignorar o prompt inteiro e desenhar personagem de anime

Sintoma mais grave que os anteriores: a imagem sai limpa (sem texto
garranchado), bem renderizada, mas **completamente fora do prompt** — em
vez da cena pedida (ex.: "trem a vapor acelerando de noite", "grãos de
areia virando microchip", "dedos digitando teclado"), saiu uma
ilustração estilo anime de uma mulher jovem em roupa justa/reveladora.
Nenhum dos três prompts tinha qualquer menção a pessoa, anime, ou o
estilo saído — não é um problema de conteúdo do prompt, é o modelo de
difusão (`krea2_turbo`) desviando pra um cluster completamente diferente
do dataset de treino, aparentemente sem gatilho identificável no input.

Reproduzido 3 vezes na mesma leva de geração (frases 2, 4 e 11 de uma
parte de 11 frases, nenhuma relação temática entre elas). Regenerar (seed
novo) resolveu nas 3 — mas como não há como prever quais frases vão sofrer
esse desvio, **isso não é opcional de revisar**: depois de qualquer geração
em lote, abra e confira visualmente CADA imagem antes de rodar
`montar_video.py`, mesmo que o script termine sem nenhum erro. "Rodou sem
erro" não é sinal de "saiu certo" aqui — mesmo tema do item 5 deste
arquivo, mas o resultado errado aqui é mais grave (conteúdo impróprio
possível) do que um zoom tremido.

## 9. img2img de continuidade de personagem (`--referencia`): denoise não solta a composição da referência de forma gradual

Contexto: `gerar_imagens.py --referencia` (Z-Image-Turbo, ver
`plano_continuidade_personagem.md` e a subseção "Continuidade de
personagem" no `CLAUDE.md`) usa `LoadImage`→`ImageScale`→`VAEEncode` como
latent inicial do `KSampler` com `denoise<1`, esperando que valores mais
altos de denoise deixem a cena nova (do prompt da frase-alvo) prevalecer
sobre a estrutura espacial da imagem de referência.

**Testado no caso real do `Video_9`** (referência = frase 7, Prometeu
acorrentado encarando a águia em pleno dia; alvo = frase 8, o fígado se
regenerando à noite, sem águia em cena), sweep em 0.35/0.5/0.65/0.8:

- Em **0.35, 0.5 e 0.65** a composição inteira da referência (pose de pé,
  a própria águia sobrevoando, céu de tempestade diurno) atravessou quase
  intacta pras três gerações — nenhuma honrou a cena nova da frase 8
  (nem a noite, nem a ausência da águia, nem o ferimento brilhando).
  0.65 ainda trouxe uns artefatos de rabisco branco espalhados pela rocha.
- Só em **0.8** a composição finalmente escapou da referência — mas nesse
  ponto a identidade também se perdeu (o personagem saiu de camisa social
  e gravata, sem a capa, num cenário de ferro-velho sem relação com a
  cena).

**Não existe um meio-termo limpo nessa faixa** (testada até 0.8) quando a
cena-alvo difere de verdade da referência em elementos concretos (objeto
em cena, hora do dia, ação) — ou a composição fica presa à referência, ou
a identidade se solta junto com ela. O mecanismo funciona bem pra manter
identidade quando a pose/cena já é parecida (mesmo ângulo, mesmo cenário
geral); pra cenas que precisam divergir de verdade, o fix manual
(reescrever o prompt da frase repetindo os descritores físicos já
estabelecidos, sem passar imagem de referência) continua mais confiável —
foi o que já resolveu esse caso específico do `Video_9` antes desse
mecanismo existir (ver `analise.md`, seção 2).

Não testei a faixa entre 0.65 e 0.8 (ex.: 0.7, 0.75) — se for retomar esse
ajuste, esse é o intervalo mais provável de conter algum ponto de
equilíbrio, se é que existe um.

**Atualização — testado em `Video_10` (mito da morte de Heitor), confirma e
piora o quadro acima**: usando uma imagem de Heitor de pé (frase 8, lança
na mão, parado) como referência pras frases 17 ("Heitor olha ao redor,
confuso, sozinho") e 22 ("Heitor cai no chão, a lança solta ao lado") —
ambas cenas de AÇÃO/POSE diferente da referência, não só elemento de cena
diferente como no caso do `Video_9`. Resultado:

- **Frase 17** (pose parecida — continua de pé, só olhando pro lado): saiu
  bem em denoise `0.5`, praticamente a mesma pose da referência mas com a
  cabeça virada — identidade perfeita, cena aceitável.
- **Frase 22** (pose bem diferente — cair no chão): em denoise `0.5` **e**
  em `0.72` (justo o intervalo não testado acima) o resultado ficou de pé,
  segurando a lança, **igual à referência** — a queda simplesmente não
  aconteceu em nenhum dos dois valores. Nem o intervalo 0.65-0.8 que
  faltava testar resolveu.

**Conclusão mais forte que a do `Video_9`**: mudança de POSE/AÇÃO (de pé →
caindo) é mais resistente ao denoise parcial do que mudança de ELEMENTO DE
CENA (presença/ausência de um objeto, dia/noite) — plausível de ser um
efeito do `steps=8` fixo do Z-Image-Turbo (Turbo = poucos passos de
sampling; com denoise<1 sobram ainda menos passos reais pro sampler
"repintar" a estrutura grossa do latent, e a silhueta de um corpo inteiro
em pé é uma estrutura espacial bem mais dominante que um objeto secundário
tipo uma águia). **Regra de uso revisada**: `--referencia` serve bem pra
reaproveitar identidade em cenas de pose/enquadramento JÁ PARECIDO com a
referência (ex.: vários planos "de pé, olhando para X") — para qualquer
frase que precise de uma AÇÃO/POSE diferente da referência (cair, correr,
lutar, deitar), não vale a pena gastar uma geração com `--referencia`: vá
direto pro fix manual (repetir os descritores físicos do personagem no
prompt daquela frase, sem imagem de referência) — foi o que resolveu a
frase 22 do `Video_10` de primeira, com a pose certa E a identidade
consistente.

## 10. Texto garranchado em arquitetura/sinalização também acontece no Z-Image-Turbo, sem nenhum passo de refino envolvido

O item 2 deste arquivo atribui o bug de texto borrado ao node `TextGenerate`
(refino de prompt, exclusivo do workflow Krea2) citando a narração como
"texto pra mostrar na tela". O workflow Z-Image-Turbo **não tem esse passo**
— o texto do prompt vai direto pro `CLIPTextEncode`, sem LLM no meio — então
a hipótese seria que esse workflow estivesse imune ao bug.

**Não está.** Testado em `Video_10`, frase 6 (`--prompts`: "elderly King
Priam... pleading with his son Hector at the gates of Troy..."): saiu uma
placa/inscrição gravada no arco do portão com letras garranchadas
formando algo como "CHARA" — sem que o prompt mencionasse texto, placa ou
inscrição em nenhum momento. Ou seja, o `KSampler` do Z-Image-Turbo pode
alucinar texto em superfícies arquitetônicas (arcos, portões, estandartes)
por conta própria, associando "cena antiga/monumental" a "tem inscrição
gravada", independente de qualquer refino de prompt.

**O que resolveu**: reescrever o prompt adicionando explicitamente `plain
stone wall background, no signage, no text, no writing` — regenerado uma
vez, saiu limpo. Não testei se `seed` novo sozinho já teria resolvido (fui
direto pra correção de prompt, seguindo a lição do item 2 de que regenerar
sem mudar o texto costuma repetir o mesmo defeito). Se esse padrão voltar a
aparecer em outras frases com cenário arquitetônico/monumental, considere
adicionar essa negação como parte do sufixo padrão do prompt em vez de
corrigir caso a caso — ainda não fiz essa mudança porque só apareceu uma
vez em ~56 gerações entre os dois projetos testados.

## 11. Deriva de armadura pra estilo medieval europeu: o fix é ancorar o período/cultura no prompt POSITIVO, não negative prompt/cfg

Sintoma (`Video_10`): frases sobre Heitor/Aquiles com prompt tipo "wearing
bronze armor and a blue cloak" saíam como cavaleiro medieval europeu de
armadura de placas cinza — nada de bronze, nada de estética grega/troiana,
mesmo o prompt dizendo "bronze armor" explicitamente.

**Hipótese testada e descartada**: que desse pra corrigir isso ligando um
negative prompt de verdade (o workflow padrão usa `ConditioningZeroOut`,
sem negative real) e subindo o `cfg` um pouco acima de `1` (`KSampler.cfg`
vem fixo em `1` no workflow t2i — nesse valor a fórmula de classifier-free
guidance colapsa pro puro positivo, `negativo + cfg*(positivo-negativo)`
com `cfg=1` = `positivo`; o negative literalmente não tem efeito nenhum
matematicamente). Testei `cfg=1.3` e `cfg=1.6` com um `CLIPTextEncode`
negativo de verdade citando "medieval European plate armor, full-face
closed helmet" explicitamente — **usando o mesmo prompt fraco que já tinha
derivado**, o resultado saiu igualzinho ao de antes: armadura medieval de
placas, mesmo com o negative dizendo pra evitar exatamente isso. Ou seja,
`cfg=1.3`/`1.6` ainda é fraco demais pra dar peso real ao negative nesse
modelo/scheduler (não testei valores mais altos por risco de degradar a
qualidade — Z-Image-Turbo foi destilado especificamente pra rodar bem em
`cfg=1`/poucos steps, e esse é justamente o motivo do
`ConditioningZeroOut` no workflow original).

**O que resolveu de verdade**: ancorar cultura/período explicitamente no
prompt POSITIVO — trocar "bronze armor" por "ancient Greek-style bronze
cuirass"/"bronze Corinthian-style helmet"/"bronze spear", e apensar "no
medieval armor" no final do próprio positivo (não como negative prompt
separado, só mais uma cláusula do texto que já vai pro `CLIPTextEncode`).
Testado isolando a variável: MESMO seed, MESMO cfg=1, SEM negative — só
trocando "bronze armor" por "ancient Greek bronze armor" no positivo já
foi suficiente pra sair com armadura de bronze grega correta,
consistentemente. **Conclusão prática**: pra esse modelo, a alavanca real
de estilo/período é a especificidade do prompt positivo, não
negative/cfg — se um elemento (arquitetura, vestimenta, armadura) sair
com o "estilo errado", primeiro tente nomear a cultura/período
explicitamente no prompt antes de mexer em cfg ou negative prompt (que
exigiria reescrever o workflow e, por esse teste, nem resolveu o
problema).

**Efeito colateral do reforço de "bronze" — cuidado pra não virar estátua**:
depois de aplicar a correção acima em todas as 28 frases do `Video_10`
(reforçando "bronze" em toda armadura/arma), duas frases especificamente
("Achilles... in bronze armor" e "an ancient Greek bronze war chariot...")
saíram com a PELE do personagem e a PELAGEM dos cavalos também com
aparência de bronze/metal (como uma estátua), não só a armadura/os
arreios. O gatilho parece ser a palavra "bronze" aparecendo perto demais
de "warrior"/"horses" sem deixar claro que só o equipamento é de bronze, a
pessoa/animal continua de carne e osso. **Corrigido** especificando
separadamente ("a man with tanned skin, wearing a bronze cuirass..."/"two
brown horses... with bronze fittings") e apensando `natural human skin
tone, not a statue` / `natural horse coats, not statues`. Ou seja, o
reforço de material tem que ser aplicado ao objeto certo (armadura, arma,
arreio) e não ao sujeito (pessoa, animal) — reforçar demais em cima do
sujeito também tende a "vazar" pra pele/pelo.
