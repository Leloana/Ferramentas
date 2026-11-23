# Roteiro do primeiro teste na GPU (RTX 4070 12 GB)

Nada desta ferramenta rodou ainda com GPU nem com os pesos reais. Este roteiro vai do
mais barato ao mais caro, para achar problema cedo. Tudo pela `teste_gpu.py`, que grava
`trabalho/teste_gpu/RESULTADOS.md` (tabela) e um `log.txt` por etapa.

## 0. Antes (uma vez, ~2 a 4 h, quase tudo download)

```powershell
cd longcat_teste
# instalação: ver README, seção "Instalação"
.\venv\Scripts\python.exe -m pytest -q tests            # tem que passar (CPU, ~6 min)
.\venv\Scripts\python.exe preparar.py clonar
.\venv\Scripts\python.exe preparar.py baixar             # ~78 GiB
.\venv\Scripts\python.exe preparar.py quantizar          # dit_distill
.\venv\Scripts\python.exe preparar.py checar
```

Na quantização, anotar o tempo e a RAM máxima no Gerenciador de Tarefas (esperado:
poucos GiB além do sistema; se passar de 20 GiB tem algo errado no streaming).

Feche navegador, ComfyUI e o que mais usar GPU/RAM.

## 1. A escada

```powershell
.\venv\Scripts\python.exe teste_gpu.py --listar
.\venv\Scripts\python.exe teste_gpu.py --ate continuacao    # primeiro só até aqui (~1 h)
```

| Etapa | O que prova | Olhar |
|---|---|---|
| `checar` | ambiente | tudo `[ok]` menos INT8 base/refino |
| `curto` | carregar no meta, offload, SDPA, VAE, texto em cache, 33 quadros | `segmentos/000.mp4` tem uma cena coerente com o prompt |
| `segmento` | 93 quadros (o tamanho real) | pico de VRAM < 11,5 GiB; minutos por segmento |
| `continuacao` | `generate_vc` + KV cache na RAM | o 2º segmento continua o 1º sem corte |
| `blocos0` | todos os blocos vindo da RAM | diferença de tempo para `segmento` = custo do offload |
| `16s` | 3 segmentos + pós (minterpolate, 720x1280) | `final.mp4` com 16 s a 30 fps; deriva de cor/rosto |
| `refino_espacial` | refino oficial 720p (BSA/triton) | se cabe; tempo; se o ganho de nitidez compensa |
| `90s` | o alvo | horas; deixar rodando; retomável |

Depois de olhar a tabela e os vídeos até `continuacao`:

```powershell
.\venv\Scripts\python.exe teste_gpu.py --so blocos0 --so 16s
.\venv\Scripts\python.exe preparar.py quantizar --variante refino
.\venv\Scripts\python.exe teste_gpu.py --so refino_espacial
.\venv\Scripts\python.exe teste_gpu.py --so 90s                # ou gerar.py com o seu prompt/roteiro
```

Argumentos depois de `--` vão para todas as etapas, ex.:
`teste_gpu.py --so segmento -- --blocos-na-gpu 16 --atencao sdpa`.

## 2. Se der problema

| Sintoma | Tentar |
|---|---|
| `CUDA out of memory` na geração | `-- --reserva-gib 6` (menos blocos fixos) ou `--blocos-na-gpu 10`; `--ffn-tokens 8192` |
| OOM só no fim do segmento (decodificação) | `--vae-tiling` |
| OOM ao codificar o texto | `--texto bf16-cpu` |
| `cudaHostRegister` falhou / RAM estoura | `--sem-pin`; fechar outros programas |
| PC travando (RAM) | o pagefile é de 2 GB: aumentar para 16 GB ou mais no Windows |
| erro de import `triton` | `pip install "triton-windows<3.3"` |
| vídeo ignora o prompt | apagar `pesos/cache_texto/` e rodar com `--texto bf16-cpu` |
| erro dentro de `flash_attn` | `--atencao sdpa` |
| erro no BSA no refino | `--refino-sem-bsa` só para confirmar que é o BSA (vai ser muito lento) |

## 3. O que anotar depois

Atualizar a seção "Tempo e memória esperados" do README com os números medidos
(`RESULTADOS.md`) e trocar o status do topo. Valores a calibrar no código:

- `RESERVA_GIB` em `lct/gerador.py` (VRAM de ativações por etapa): usar o pico medido
  em `segmento` menos o que os blocos ocupam, com ~0,5 GiB de folga.
- Se SDPA for muito mais lento que o esperado, vale tentar uma wheel de flash-attn
  para Windows (torch 2.6 + cu124 + a versão do Python do venv).

Comparações que valem um vídeo cada (mesmo prompt e seed):
- `--modo distill` x `--modo completo` em 1 segmento (precisa da variante base).
- sem refino x `--refino espacial` em 1 segmento.
- `--texto int8-gpu` x `--texto bf16-cpu`.
