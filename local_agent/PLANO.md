# PLANO.md — Agente de IA Local

> Documento de orientação de implementação para ser executado pelo Claude.
> **Escopo:** SOMENTE o agente local. Escalonamento para APIs frontier (Claude/GPT) está **fora de escopo** neste plano.

---

## 1. Objetivo

Implementar um **agente local com tool calling**, rodando 100% na máquina do usuário, capaz de executar tarefas **escopadas e de cadeia curta** (chamadas de ferramenta pontuais, RAG simples, extração/classificação, loops ReAct curtos).

**Não é objetivo** deste agente: autonomia longa multi-passo, orquestração de muitas ferramentas em cadeias longas, ou autocorreção em horizonte longo. Se a tarefa exigir isso, o agente deve **falhar de forma limpa** (ver seção 7), não insistir.

---

## 2. Restrições de hardware (imutáveis)

- **GPU:** NVIDIA RTX 4070, **12 GB VRAM**.
- Tudo (pesos + KV cache + overhead) **precisa caber na VRAM**. Se estourar, o runtime faz offload para RAM e a velocidade despenca para ~1–2 tokens/s — inaceitável.
- Reservar **~1,5 GB fixos** para contexto CUDA + ativações.
- Orçamento efetivo: `12 GB − pesos − 1,5 GB = VRAM disponível para KV cache`.

---

## 3. Modelo

**Primário:** `Qwen 3.5 9B` — quantização **Q4_K_M**.
- Justificativa: melhor tool-caller confiável que cabe folgado em GPU única de 12 GB (BFCL V4 ~66%). Deixa espaço para contexto.
- Footprint aproximado dos pesos em Q4_K_M: ~6 GB.

**Alternativas aceitáveis (nesta ordem):**
1. `Qwen3 8B` (Q4_K_M) — ~5 GB de pesos, ainda mais contexto disponível; excelente em tool calling.
2. `Gemma 3 12B` / `Gemma 4 12B` (Q4_K_M) — alternativa se o usuário preferir o ecossistema Google.

**Ação obrigatória antes de fixar:** verificar no Hugging Face / Ollama se saiu uma versão pequena mais nova da família Qwen (ex.: um Qwen 3.6 na faixa 8–14B) que caiba em 12 GB. Se sim, priorizar a mais recente com tool calling nativo.

**Regra de quantização:** nunca abaixo de Q4_K_M. Um modelo menor em Q5 é melhor que um maior em Q3. Não perseguir 32B/70B nesta placa.

---

## 4. Runtime

**Recomendado: Ollama** (facilita servir via API OpenAI-compatível, que é o que o loop do agente vai consumir).

Alternativa: `llama.cpp` (mais controle) ou LM Studio (mais visual, bom para testes manuais).

### 4.1 Otimizações de VRAM (obrigatórias)

Estas três configurações são o que permite equilibrar contexto × parâmetros:

- **KV cache em Q8_0** — praticamente sem perda de qualidade, corta o KV cache pela metade → **dobra o contexto disponível**.
- **Flash Attention ligado** — reduz memória e acelera.
- **Contexto explícito (`num_ctx`)** — NUNCA deixar o runtime pré-alocar o máximo (ex.: 128K). Definir o valor real necessário (ver seção 5).

### 4.2 Variáveis de ambiente / config Ollama

```bash
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
```

Modelfile de exemplo (ajustar `num_ctx` conforme seção 5):

```
FROM qwen3.5:9b-instruct-q4_K_M
PARAMETER num_ctx 24576
PARAMETER temperature 0.3
PARAMETER top_p 0.9
```

> `temperature` baixa (0.2–0.4): tool calling e output estruturado exigem determinismo, não criatividade.

### 4.3 ⚠️ Armadilha crítica: chat template

O maior motivo de falha em tool calling local **não é o modelo, é o chat template mal implementado no servidor**. Antes de qualquer outra coisa:
- Confirmar que o runtime aplica o **template de tool calling nativo do Qwen** corretamente.
- Validar com um teste mínimo de 1 tool call (ver seção 8) **antes** de construir o loop do agente.
- Se as chamadas vierem malformadas, o problema é quase sempre o template/serving — não trocar de modelo antes de descartar isso.

---

## 5. Orçamento de contexto (contexto × parâmetros)

Custo aproximado do KV cache **com Q8**: ~0,07 GB por 1.000 tokens para um modelo ~9B.

Com `Qwen 3.5 9B Q4_K_M` (~6 GB de pesos):
- VRAM p/ KV = `12 − 6 − 1,5 ≈ 4,5 GB`
- Contexto viável com KV em Q8 ≈ **~50K tokens**

**Definir `num_ctx` conforme a necessidade real** (não maior que o preciso):
- Agente com poucas ferramentas e cadeias curtas: `num_ctx = 16384` a `24576` é suficiente e sobra VRAM.
- Se precisar de histórico/RAG maior: subir gradualmente e monitorar VRAM.

> Lembrete de design: **loops agênticos consomem contexto rápido** — cada schema de ferramenta + cada resultado de tool call se acumula na janela. Preferir modelo 8–9B com contexto folgado a um 14B espremido; contexto insuficiente é o que mais quebra agentes pequenos.

---

## 6. Arquitetura do agente

Padrão **ReAct** simples (raciocínio → tool call → observação → repetir), consumindo o endpoint OpenAI-compatível do Ollama.

Considerar o framework **Qwen-Agent** (recomendado pela Alibaba) para maximizar a confiabilidade das chamadas; ou implementar loop próprio com function calling OpenAI-compatível.

### 6.1 Princípios de design (não negociáveis)

1. **Conjunto pequeno de ferramentas** — idealmente 3 a 6. Quanto mais ferramentas, pior a seleção do modelo pequeno.
2. **Schemas claros e explícitos** — nomes descritivos, descrições curtas, parâmetros tipados. O modelo pequeno depende disso.
3. **Cadeias curtas** — quanto mais escopada a tarefa, melhor a performance.
4. **Output estruturado sempre validado** antes de executar a ferramenta.

### 6.2 Esqueleto do loop (Python, OpenAI-compatível)

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

MODEL = "qwen3.5:9b-instruct-q4_K_M"
MAX_ITERS = 6          # guardrail: cadeia curta (ver seção 7)

tools = [
    # 3–6 ferramentas com schema JSON claro. Exemplo:
    {
      "type": "function",
      "function": {
        "name": "buscar_arquivo",
        "description": "Busca arquivos por nome em um diretório.",
        "parameters": {
          "type": "object",
          "properties": {
            "diretorio": {"type": "string"},
            "padrao": {"type": "string"}
          },
          "required": ["diretorio", "padrao"]
        }
      }
    },
]

def run_agent(user_msg: str):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    for i in range(MAX_ITERS):
        resp = client.chat.completions.create(
            model=MODEL, messages=messages, tools=tools, temperature=0.3
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            return msg.content   # resposta final

        for call in msg.tool_calls:
            result = dispatch_tool(call)          # validar args ANTES de executar
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": result,
            })
    # estourou o limite de iterações -> falha limpa (seção 7)
    return "FALHA: tarefa excedeu o limite de passos do agente local."
```

### 6.3 System prompt (diretrizes)

- Definir o papel e o escopo com clareza.
- Instruir a usar ferramentas apenas quando necessário.
- Instruir a **parar e reportar** se a tarefa exigir mais passos que o razoável, em vez de improvisar.

---

## 7. Guardrails (obrigatórios)

1. **Limite de iterações** (`MAX_ITERS`, ex.: 6). Ao atingir, encerrar com mensagem de falha clara.
2. **Timeout por tool call** e timeout global da tarefa.
3. **Validação de argumentos** contra o schema JSON **antes** de executar qualquer ferramenta (nunca confiar cegamente no output do modelo).
4. **Whitelist de ferramentas** — o agente só executa funções pré-registradas.
5. **Sandbox** para ferramentas que tocam sistema de arquivos / rede — restringir a diretórios/hosts permitidos.
6. **Detecção de loop** — se o modelo repetir a mesma tool call com os mesmos args, abortar.
7. **Falha limpa** — quando o agente não consegue concluir, retornar erro explícito, não alucinar sucesso.

---

## 8. Critérios de aceitação / testes

Antes de considerar pronto, validar em ordem:

1. **Smoke test de serving:** o modelo carrega inteiro na VRAM (checar com `nvidia-smi`, deve estar abaixo de 12 GB) e responde a um prompt simples.
2. **Teste de 1 tool call:** uma pergunta que exige exatamente uma chamada → verificar que a chamada vem **bem formatada** (nome correto, args válidos no schema). Se falhar aqui, é problema de chat template (seção 4.3).
3. **Teste de seleção de ferramenta:** dado um conjunto de 3–6 ferramentas, o modelo escolhe a correta em ≥ 8 de 10 casos.
4. **Teste de cadeia curta (2–3 passos):** ex.: buscar → ler → resumir. Verificar que passa os resultados corretamente entre passos.
5. **Teste de guardrail:** dar uma tarefa impossível/ambígua e confirmar que o agente **falha limpo** dentro de `MAX_ITERS`, sem loop infinito nem alucinação de sucesso.
6. **Teste de VRAM sob carga:** rodar com `num_ctx` no valor de produção e uma cadeia real; confirmar que não há offload para RAM (velocidade estável).

---

## 9. Entregáveis esperados

1. Script/config de setup do runtime (Modelfile do Ollama + variáveis de ambiente).
2. Módulo do agente com o loop ReAct, registro de ferramentas e guardrails.
3. Conjunto inicial de 3–6 ferramentas com schemas.
4. Suíte de testes cobrindo a seção 8.
5. README curto: como iniciar o servidor, rodar o agente e rodar os testes.

---

## 10. O que NÃO fazer

- ❌ Não usar quantização abaixo de Q4_K_M.
- ❌ Não tentar rodar modelos 32B/70B nesta placa.
- ❌ Não pré-alocar contexto máximo (128K) sem necessidade.
- ❌ Não registrar dezenas de ferramentas — degrada a seleção.
- ❌ Não desenhar cadeias longas/autônomas — fora do escopo do agente local.
- ❌ Não trocar de modelo antes de descartar problema de chat template.
- ❌ Não implementar escalonamento para API frontier — fora de escopo deste plano.
