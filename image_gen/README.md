# 🎨 Image Gen — Geração de Imagens com ComfyUI

Este módulo contém workflows em formato de API para o **ComfyUI** e guias para geração de imagens via modelos locais de difusão.

---

## 🛠️ Workflows Disponíveis

### 1. `image_krea2_turbo_t2i.json`
* **Modelo:** Krea2 Turbo (`krea2_turbo`).
* **Tipo:** Text-to-Image (T2I) ultrarrápido.
* **Resolução / Aspect Ratio:** Suporta múltiplos formatos (1:1, 16:9, 9:16 vertical, etc.) e ajuste fino de megapixels.
* **Saída:** As imagens geradas devem ser salvas na pasta [`resultados/`](./resultados/) (já ignorada no Git).

---

## 📖 Como Usar

Para instruções detalhadas de como carregar o JSON de workflow, configurar parâmetros (prompt, seed, aspect ratio) e enviar requisições para a API local do ComfyUI (`http://127.0.0.1:8188`), consulte:

👉 **[HOW_TO_USE.md](./HOW_TO_USE.md)**
