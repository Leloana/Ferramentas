# 📁 Convenções de Path no Bash (Windows)

## ⚠️ IMPORTANTE: Sempre usar forward slashes (`/`) no Bash/PowerShell

### ❌ **ERRADO:**
```bash
ls path\to\file
cd path\to\file
cp /home/user/file.txt /backup/path\to\file
```

### ✅ **CERTO:**
```bash
ls -la C:/Users/mf827/Documents/Ferramentas/karaoke/client/
dir C:/Users/mf827/Documents/Ferramentas/karaoke/server
cd C:/Users/mf827/Documents/Ferramentas/karaoke/server
```

---

## 🎯 **Regra de Ouro**
- **Windows Paths no Bash:** SEMPRE usar `/` (forward slash), não `\`
- **PowerShell:** Pode usar ambos, mas preferir `/` para compatibilidade com Bash
- **Paths absolutos:** `C:/Users/mf827/Documents/Ferramentas/karaoke/`
- **Paths relativos:** Mantê-los sem drive letter (ex: `./server/routes/`)

---

## 📝 **Exemplos de Uso Comum**

### Listar arquivos
```bash
ls -la C:/Users/mf827/Documents/Ferramentas/karaoke/client/
```

### Navegar entre pastas
```bash
cd C:/Users/mf827/Documents/Ferramentas/karaoke/server/
```

### Comandos com múltiplos paths
```bash
cp tools/**/*.py C:/Users/mf827/Documents/Ferramentas/karaoke/server/utils/
mkdir -p "C:/Users/mf827/Documents/Ferramentas/karaoke/client/styles"
```

### Git no Windows Bash
```bash
git add C:/path/to/file.js
git commit -m "feat: descricao"
git push
```

---

## 🔧 **Comandos Específicos por Projeto**

### Karaoke
```bash
# Ativar venv
C:/Users/mf827/Documents/Ferramentas/karaoke/venv/Scripts/Activate.ps1

# Executar
uvicorn server.main:app --host 192.168.15.6 --port 8000
```

### Rodar testes
```bash
C:/Users/mf827/Documents/Ferramentas/karaoke/venv/Scripts/python.exe -m unittest discover -s tests
```