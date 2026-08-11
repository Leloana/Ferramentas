# Como usar esta ferramenta (gerador de imagens Krea2 Turbo)

Guia para um modelo de IA (não humano) usar o arquivo `image_krea2_turbo_t2i.json`
desta pasta e gerar uma imagem a partir de texto. Siga os passos NA ORDEM. Não
pule etapas, não invente endpoints diferentes dos listados aqui.

## O que é isto

`image_krea2_turbo_t2i.json` é um **workflow do ComfyUI em formato API**
(não é a interface gráfica — é um JSON que você manda por HTTP). Ele recebe um
texto e devolve uma imagem gerada pelo modelo de difusão `krea2_turbo`.

Toda imagem gerada deve ser salva na pasta `resultados/` (mesma pasta deste
guia). Essa pasta já existe e está no `.gitignore` — não crie outra pasta de
saída.

## Pré-requisito (obrigatório, confira antes de tudo)

O ComfyUI precisa estar aberto e rodando localmente. Confirme com:

```
GET http://127.0.0.1:8188/system_stats
```

Se essa chamada falhar (conexão recusada), **pare e avise o usuário** — não
tem como gerar imagem sem o ComfyUI aberto. Não tente "descobrir" outra porta
ou servidor por conta própria.

## Passo a passo

1. Leia o arquivo `image_krea2_turbo_t2i.json` (está nesta mesma pasta) e
   carregue como JSON em memória.
2. Faça uma **cópia** desse JSON em memória. Edite só a cópia. **Nunca
   sobrescreva o arquivo `image_krea2_turbo_t2i.json` no disco.**
3. Na cópia, edite os campos da tabela abaixo (as chaves `"30:19"`, `"49"`
   etc. são IDs de nó — chaves de primeiro nível do JSON):

   | Quero mudar | Nó | Campo dentro de `inputs` | Tipo | Exemplo |
   |---|---|---|---|---|
   | O prompt (texto da imagem) | `30:19` | `value` | string | `"a red fox sitting in the snow, forest background"` |
   | Formato/proporção da imagem | `49` | `aspect_ratio` | string (uma das opções abaixo) | `"16:9 (Widescreen)"` |
   | Tamanho da imagem | `49` | `megapixels` | float, 0.1 a 16.0 | `1.0` |
   | Semente aleatória | `30:3` | `seed` | int, 0 a 2^32-1 | um número aleatório novo a cada geração |

   Valores válidos de `aspect_ratio` (nó `49`): `"1:1 (Square)"`,
   `"2:3 (Portrait Photo)"`, `"3:2 (Photo)"`, `"3:4 (Portrait Standard)"`,
   `"4:3 (Standard)"`, `"9:16 (Portrait Widescreen)"`, `"16:9 (Widescreen)"`,
   `"21:9 (Ultrawide)"`.

   Deixe **todos os outros campos do JSON exatamente como estão** (inclusive
   `30:24`, `30:23` — já vêm `false` por padrão, o que é o modo recomendado;
   veja "Recursos opcionais" no fim se quiser mexer neles).

4. Antes de enviar, aplique as regras da seção **"Regras do prompt"** abaixo
   ao texto que você colocou em `30:19`.
5. Envie a cópia editada:

   ```
   POST http://127.0.0.1:8188/prompt
   Body (JSON): {"prompt": <o JSON inteiro editado>}
   ```

   A resposta traz `"prompt_id"`. Guarde esse valor. Se a resposta tiver a
   chave `"node_errors"` com conteúdo, algo no JSON está errado — pare e
   reporte o erro, não tente adivinhar um conserto.
6. Espere a imagem ficar pronta, checando a cada ~2 segundos:

   ```
   GET http://127.0.0.1:8188/history/<prompt_id>
   ```

   Quando `<prompt_id>.status.completed == true` na resposta, terminou. Se
   `<prompt_id>.status.status_str == "error"`, a geração falhou — leia
   `status.messages` e pare (não insista tentando de novo automaticamente).
   Timeout sugerido: 10 minutos (a geração pode demorar bastante dependendo
   da máquina).
7. Pegue os dados do arquivo gerado em
   `<prompt_id>.outputs["29"].images[0]` (tem `filename`, `subfolder`, `type`).
8. Baixe a imagem final:

   ```
   GET http://127.0.0.1:8188/view?filename=<filename>&subfolder=<subfolder>&type=<type>
   ```

   Salve o conteúdo binário da resposta como `.png` dentro da pasta
   `resultados/` (mesma pasta deste guia). **Todas as imagens geradas devem
   ir para `resultados/`** — não salve na raiz de `image_gen/` nem em outra
   pasta. `resultados/` está no `.gitignore` do repositório (não é
   versionado), então pode gerar à vontade sem sujar o git.

## Script Python pronto (copie, troque só o PROMPT e rode)

```python
import copy, json, random, time, requests

SERVER = "http://127.0.0.1:8188"
WORKFLOW_PATH = "image_krea2_turbo_t2i.json"  # este arquivo, mesma pasta

PROMPT = "a red fox sitting in the snow, forest background"  # <-- troque aqui
ASPECT_RATIO = "16:9 (Widescreen)"  # veja lista de opções válidas no guia
OUTPUT_FILE = "resultados/saida.png"  # sempre dentro de resultados/

with open(WORKFLOW_PATH, encoding="utf-8") as f:
    workflow = json.load(f)

wf = copy.deepcopy(workflow)
wf["30:19"]["inputs"]["value"] = PROMPT
wf["49"]["inputs"]["aspect_ratio"] = ASPECT_RATIO
wf["30:3"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)

resp = requests.post(f"{SERVER}/prompt", json={"prompt": wf}, timeout=30)
resp.raise_for_status()
data = resp.json()
if data.get("node_errors"):
    raise RuntimeError(data["node_errors"])
prompt_id = data["prompt_id"]

entry = None
inicio = time.monotonic()
while time.monotonic() - inicio < 600:
    hist = requests.get(f"{SERVER}/history/{prompt_id}", timeout=30).json()
    entry = hist.get(prompt_id)
    if entry:
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(status.get("messages"))
        if status.get("completed"):
            break
    time.sleep(2)
else:
    raise TimeoutError("ComfyUI não terminou a tempo")

img = entry["outputs"]["29"]["images"][0]
r = requests.get(f"{SERVER}/view", params={
    "filename": img["filename"],
    "subfolder": img.get("subfolder", ""),
    "type": img.get("type", "output"),
}, timeout=60)
r.raise_for_status()
with open(OUTPUT_FILE, "wb") as f:
    f.write(r.content)
print(f"Imagem salva em {OUTPUT_FILE}")
```

## Regras do prompt (obrigatórias — aprendidas gerando centenas de imagens reais)

1. **Escreva o prompt em inglês.** O modelo funciona de forma mais confiável
   em inglês. Não misture português no meio do texto em inglês.
2. **Se a cena tiver pessoas, descreva a roupa explicitamente**, mesmo que
   pareça óbvio. Sem isso, o modelo tende a desenhar a pessoa nua/parcialmente
   nua por padrão. Termine o prompt com algo como:
   `, fully clothed, appropriate attire, no nudity`
3. **Não peça texto, placas, letreiros ou legendas na imagem**, a menos que
   seja realmente necessário. Modelos de difusão desenham texto malformado
   ("garranchado"). Se a cena tem arquitetura/monumentos e você quer evitar
   letras aparecendo sozinhas na parede, adicione algo como:
   `, no text, no signage, no writing`
4. **Prefira `"16:9 (Widescreen)"`** quando não houver exigência de formato
   vertical. Formatos verticais (`9:16`, `3:4`) têm taxa de defeito bem maior
   (rotação errada, cena duplicada em painéis) neste modelo.
5. **Escreva um prompt curto e concreto** (uma frase objetiva descrevendo a
   cena), não um parágrafo longo cheio de detalhes simultâneos. Prompts
   longos aumentam alucinação (membros extras, painéis duplicados),
   principalmente em formato vertical.
6. **Nomeie cultura/período histórico explicitamente quando importar**
   (ex.: escreva `"ancient Greek bronze armor"`, não só `"armor"`). Sem isso
   o modelo tende a "escorregar" para o estilo genérico mais comum (ex.:
   armadura medieval europeia) mesmo quando o prompt pede outra coisa.
   Não adianta tentar excluir um estilo — este workflow não tem negative
   prompt real (o `cfg` está fixo em `1`, o que matematicamente anula
   qualquer negative). A única forma de evitar algo é reforçar o oposto no
   próprio prompt positivo.
7. **Sempre confira a imagem depois de gerada.** "Terminou sem erro" não
   garante que o conteúdo está certo — o modelo pode ocasionalmente ignorar
   o prompt inteiro e desenhar outra coisa. Se a imagem saiu errada, gere de
   novo com uma seed nova (passo 3 do script já randomiza a seed a cada
   chamada).
8. **Se a mesma falha se repetir 2 vezes seguidas com o mesmo prompt, pare
   de tentar seed nova — reescreva o prompt.** Algumas construções de frase
   (ex. "X transitioning into Y") causam falha de forma consistente, não por
   azar de amostragem.

## Recursos opcionais (não mexa a menos que seja pedido explicitamente)

- **Refino automático de prompt** (nó `30:24`, campo `value`): se `true`, um
  modelo de linguagem (`qwen3vl`, nó `30:16`) reescreve seu texto numa
  descrição mais rica antes de gerar a imagem. Isso pode ajudar prompts
  curtos/vagos, mas também pode introduzir os problemas de texto garranchado
  descritos na regra 3 acima (o refino às vezes interpreta frases
  declarativas como "pedido de legenda"). Padrão do arquivo: `false`
  (usa seu texto literal). Só ligue se o usuário pedir explicitamente.
- **LoRA de estilo** (nós `30:23`, `42`, `30:15`): aplica um estilo visual
  extra (ex. aquarela, tons pastel) por cima do modelo base. Desligado por
  padrão (`30:23.value = false`). Neste ambiente, **só o arquivo
  `krea2_warmpastel.safetensors` está confirmado instalado** — as outras
  opções listadas no nó `42` (`krea2_coolblue`, `krea2_darkbrush`,
  `krea2_plasmoid`) podem não existir no disco e vão falhar a geração. Não
  ative isso a menos que o usuário peça um estilo específico.

## O que cada nó faz (referência rápida — não precisa decorar)

| Nó | Função |
|---|---|
| `30:19` | Seu prompt (texto de entrada) |
| `30:18` | System prompt do refino automático (só é usado se `30:24=true`) |
| `30:24` | Liga/desliga o refino automático do prompt |
| `30:16` | O modelo de linguagem que faz o refino (`qwen3vl_4b`) |
| `49` | Resolução/formato final da imagem |
| `30:3` | Gerador de imagem (KSampler) — 8 passos, `cfg=1` (modelo "turbo") |
| `30:10` / `30:11` / `30:12` | Carregam os modelos de difusão, CLIP e VAE — não mexer |
| `30:23` / `42` / `30:15` | LoRA de estilo opcional (desligado por padrão) |
| `29` | Salva a imagem final (prefixo do nome de arquivo: `Krea2_turbo`) |
