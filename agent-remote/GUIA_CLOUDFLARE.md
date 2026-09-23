# ☁️ Guia de Uso do Cloudflare Tunnel (`cloudflared`)

O **Cloudflare Tunnel** é o componente responsável por permitir que você acesse a interface web do **Agent-Remote** a partir de qualquer lugar (via 4G/5G no celular ou outro computador) sem precisar:
* Abrir portas no seu roteador (sem port forwarding).
* Ter um IP público fixo.
* Configurar DDNS (Dynamic DNS).
* Expor o IP real da sua casa para a internet.

---

## ⚡ Como Funciona

Ao iniciar um túnel, o aplicativo `cloudflared` que roda no seu PC estabelece uma **conexão segura de dentro para fora (outbound)** diretamente com os datacenters globais da Cloudflare pela porta 443. 

Quando você acessa o endereço gerado pelo celular, a Cloudflare recebe a requisição com certificado SSL/HTTPS válido e a repassa diretamente pelo túnel para o servidor FastAPI local do seu PC.

```
[Seu Celular] ──(HTTPS)──► [Cloudflare Edge] ──(Túnel Reverso Seguro)──► [Seu PC (FastAPI)]
```

---

## 🚀 Modos de Túnel Suportados

### Modo 1: Quick Tunnel (Padrão — Zero Configuração)
* **Requisitos:** Apenas ter o executável do `cloudflared` instalado no PC.
* **Custo:** 100% gratuito.
* **Conta na Cloudflare:** Não necessária! Você não precisa se cadastrar, não precisa de cartão de crédito e não precisa ter domínio.
* **Como funciona:** O Cloudflare gera uma URL temporária aleatória com terminação oficial:
  `https://palavra-aleatoria-123.trycloudflare.com`
* **Tempo de vida:** Permanece ativa enquanto o script do Agent-Remote estiver aberto. Ao fechar o terminal, a URL é destruída imediatamente.

### Modo 2: Named Tunnel (Opcional — Link Fixo e Permanente)
* **Requisitos:** Uma conta gratuita na Cloudflare e um domínio próprio adicionado lá (ex: `seudominio.com`).
* **Vantagem:** O endereço nunca muda (ex: `https://agente.seudominio.com`).
* **Configuração:**
  Basta informar o seu token no arquivo `config.json`:
  ```json
  {
    "cloudflare": {
      "mode": "named",
      "tunnel_token": "SEU_TOKEN_AQUI"
    }
  }
  ```

---

## 📥 Como Instalar o `cloudflared` na sua Máquina

O `cloudflared` é um executável leve e oficial mantido pela própria Cloudflare. Instale apenas uma vez:

### No Windows:
Abra o PowerShell como Administrador e execute:
```powershell
winget install --id Cloudflare.cloudflared
```
*Ou baixe diretamente o `cloudflared.exe` da [página de releases do GitHub oficial](https://github.com/cloudflare/cloudflared/releases) e coloque em uma pasta dentro do seu PATH.*

### No Linux (Ubuntu / Debian):
```bash
# 1. Adicionar o repositório oficial da Cloudflare
sudo mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list

# 2. Instalar
sudo apt update && sudo apt install cloudflared
```

### Validar se a instalação deu certo:
Execute no terminal:
```bash
cloudflared --version
```
Se exibir a versão instalada (ex: `cloudflared version 2024.x.x`), está pronto!

---

## 🤖 Automação no Agent-Remote

Você **não precisa** rodar comandos manuais do `cloudflared` no dia a dia.

Quando você executa o inicializador:
```bash
python run.py
```
O script:
1. Detecta automaticamente se o `cloudflared` está instalado.
2. Inicia o servidor local FastAPI na porta `8765`.
3. Dispara o Quick Tunnel em segundo plano:
   `cloudflared tunnel --url http://127.0.0.1:8765`
4. Lê os logs em tempo real e captura a URL pública `.trycloudflare.com`.
5. Exibe a URL formatada no terminal e gera um **QR Code ASCII** para você conectar o celular em 2 segundos.
6. Ao pressionar `Ctrl+C`, finaliza tanto o servidor quanto o processo do túnel de forma limpa.
