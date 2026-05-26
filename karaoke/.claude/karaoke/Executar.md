### Karaoke AI Premium
* **Ambiente:** `cd karaoke; .\venv\Scripts\Activate.ps1`
* **Executar Servidor (HTTPS com rede local):**
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }; .\venv\Scripts\Activate.ps1; uvicorn server.main:app --host 192.168.15.6 --port 8000 --reload --ssl-keyfile "server/key.pem" --ssl-certfile "server/cert.pem"
  ```
* **Executar Testes Unitários:**
  ```powershell
  .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
  ```