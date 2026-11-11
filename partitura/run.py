"""Sobe a Partitura em http://127.0.0.1:8030 (--lan abre na rede local): buscar, gerar (AMT-APC, modo leve) e ler."""
import sys
import webbrowser

import uvicorn

if __name__ == "__main__":
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    if "--sem-navegador" not in sys.argv:
        webbrowser.open("http://127.0.0.1:8030")
    uvicorn.run("web.servidor:app", host=host, port=8030)
