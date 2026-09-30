"""Configuração comum dos testes (pytest carrega antes dos módulos de teste)."""
import os
import tempfile

# Perfis de cantores numa pasta temporária: os testes de WebSocket gravavam
# "PlayerOne" e "WS Song" nos perfis reais (players/).
os.environ.setdefault("KARAOKE_PLAYERS_DIR", tempfile.mkdtemp(prefix="karaoke-players-"))
