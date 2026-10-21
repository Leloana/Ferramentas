"""Sobe o app de figurinhas. Uso: python run.py [--lan]  (--lan libera para o celular na rede)."""
import sys

import uvicorn

if __name__ == "__main__":
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    print(f"Figurinhas em http://{'<ip-do-pc>' if host == '0.0.0.0' else '127.0.0.1'}:8020")
    uvicorn.run("server:app", host=host, port=8020)
