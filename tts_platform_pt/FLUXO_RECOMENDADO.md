# Fluxo de Trabalho Recomendado: Produção Automatizada de Vídeos

Este guia consolida o fluxo oficial e recomendado para executar a produção completa de vídeos históricos (Anime e Realista) na máquina com a **Nvidia RTX 4070 (12GB VRAM)**.

---

## 1. Na Máquina de Desenvolvimento (Antes de ir para a Máquina de GPU)
Garantir que os últimos scripts e documentações estejam sincronizados no GitHub:
```bash
git push origin main
```

---

## 2. Na Máquina de Execução (Com a GPU RTX 4070)

### Passo 1: Atualizar o Repositório Local
Abra o terminal na pasta do projeto e puxe as novidades:
```bash
cd /caminho/do/projeto/tts_platform_pt
git pull origin main
```

---

### Passo 2: Download dos Modelos Qwen-Image-2.1 (Apenas na 1ª vez)
Execute o script automatizado com suporte a continuação de download (pesos INT8 `int8_convrot` otimizados para consumir ~8.5GB VRAM no ComfyUI, sem estourar os 12GB da 4070):
```bash
python3 scripts/download_qwen_models.py
```
> **Nota**: O script detecta automaticamente a instalação padrão do ComfyUI. Se seu ComfyUI estiver em um caminho customizado, use:
> `python3 scripts/download_qwen_models.py --comfy-dir /caminho/para/ComfyUI`

---

### Passo 3: Iniciar os Serviços Locais (2 Terminais)

*   **Terminal 1 — Servidor de Voz XTTS-v2**:
    ```bash
    uvicorn server.main:app --port 8011
    ```
    *(Aguarda inicialização até exibir `Uvicorn running on http://127.0.0.1:8011`)*.

*   **Terminal 2 — ComfyUI Desktop ou Core**:
    *   Inicie o aplicativo ComfyUI Desktop ou o script `main.py` do ComfyUI na porta padrão `8188` (`http://127.0.0.1:8188`).

---

### Passo 4: Produção Automatizada em 1 Comando (`executar_projeto.py`)

Criamos o orquestrador [`scripts/executar_projeto.py`](scripts/executar_projeto.py) que executa todo o pipeline em sequência (Áudio XTTS + Alinhamento -> Geração Qwen-Image-2.1 com continuidade -> Montagem final 9:16 com zoom e legendas queimadas):

#### A. Produzir o Vídeo Oficial (Video_11 — Miyamoto Musashi):
```bash
# Parte 1: O Duelo na Ilha de Ganryujima (~50s)
python3 scripts/executar_projeto.py Projetos/Video_11/musashi_duelo_ganryujima

# Parte 2: O Golpe do Remo (~50s) - Reutiliza a consistência visual de Musashi
python3 scripts/executar_projeto.py Projetos/Video_11/musashi_duelo_ganryujima_parte2
```

#### B. Produzir Projetos do Acervo Histórico (`Projetos/ideias/`):

**🎨 Estilo Anime Cinematográfico (Makoto Shinkai / Wit Studio):**
```bash
# Bruxas da Noite (1942) - Pilotos soviéticas de Po-2
python3 scripts/executar_projeto.py Projetos/ideias/bruxas_da_noite_1942

# Batalha das Termópilas (480 a.C.) - Leônidas e os 300
python3 scripts/executar_projeto.py Projetos/ideias/batalha_das_termopilas_480ac

# Samurai Negro Yasuke (1581) - Yasuke e Nobunaga
python3 scripts/executar_projeto.py Projetos/ideias/samurai_negro_yasuke_1581

# Tomoe Gozen (1183) - A lendária onna-musha
python3 scripts/executar_projeto.py Projetos/ideias/tomoe_gozen_kurikara_1183

# Carga dos Hussardos Alados (1683) - Batalha de Viena
python3 scripts/executar_projeto.py Projetos/ideias/carga_dos_hussardos_1683
```

**🎥 Estilo Realista (Docudrama / Cinematografia Histórica):**
```bash
# Mergulhadores de Chernobyl (1986)
python3 scripts/executar_projeto.py Projetos/ideias/mergulhadores_de_chernobyl_1986

# Os Minutos Finais do Titanic (1912)
python3 scripts/executar_projeto.py Projetos/ideias/minutos_finais_titanic_1912

# O Resgate de Dunkirk (1940)
python3 scripts/executar_projeto.py Projetos/ideias/resgate_de_dunkirk_1940

# Abertura da Tumba de Tutancâmon (1922)
python3 scripts/executar_projeto.py Projetos/ideias/abertura_tumba_tutancamon_1922

# O Voo Solo de Lindbergh (1927)
python3 scripts/executar_projeto.py Projetos/ideias/voo_de_lindbergh_1927
```

---

## 3. Opções Úteis do `executar_projeto.py`

Se você quiser rodar apenas etapas específicas ou alterar parâmetros:

| Comando | Descrição |
| :--- | :--- |
| `--pular-audio` | Usa o áudio e manifesto já gerados anteriormente e roda apenas imagens e montagem. |
| `--pular-imagens` | Roda apenas o áudio e a montagem (útil para testar legendas rapidamente). |
| `--pular-montagem` | Gera o áudio e as imagens sem renderizar o vídeo `.mp4`. |
| `--voz "Nome da Voz"` | Sobrescreve a voz indicada no `vozes.md` (ex: `--voz "Tais Galante"` para feminino). |
| `--velocidade 1.15` | Ajusta o ritmo da fala do XTTS (padrão é 1.20). |

---

## 4. Onde Encontrar o Vídeo Final
O vídeo montado com proporção 9:16 vertical, legendas animadas em amarelo/branco e transições de câmera será salvo diretamente em:
`Projetos/<nome_do_projeto>/video/texto_9x16.mp4`
Pronto para publicação direta no TikTok, Instagram Reels e YouTube Shorts.
