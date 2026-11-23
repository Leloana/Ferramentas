"""Ferramenta de teste do LongCat-Video numa GPU de 12 GB (RTX 4070) com 32 GB de RAM.

Módulos:
    vendor     - acha e importa o código oficial (clonado em vendor/LongCat-Video)
    quantizar  - converte o DiT bf16 em INT8 shard a shard, fundindo LoRA se pedido
    carregar   - monta o DiT INT8 sem alocar os pesos bf16 e o pipeline com texto em cache
    offload    - mantém N blocos do DiT na GPU e traz o resto da RAM bloco a bloco
    patches    - atenção via SDPA (sem flash-attn), FFN em pedaços, roda sem torch.distributed
    texto      - codifica os prompts com o UMT5 uma vez e guarda em disco
    plano      - conta de segmentos para N segundos e roteiro de prompts por trecho
    video_io   - grava/lê segmentos, concatena e faz o pós (ffmpeg)
    memoria    - medição de VRAM/RAM para os testes
"""

FPS_BASE = 15          # o LongCat gera a 15 fps no estágio 1
QUADROS_SEGMENTO = 93  # quadros por chamada (4k+1)
QUADROS_COND = 13      # quadros do fim do segmento anterior usados como condição
COMMIT_LONGCAT = "58eb336edc5c8c63389838727e40b8c18434e54e"
REPO_LONGCAT = "https://github.com/meituan-longcat/LongCat-Video"
