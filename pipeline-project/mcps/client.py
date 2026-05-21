"""
Cliente MCP genérico.
Gerencia um subprocesso de servidor MCP stdio e expõe métodos para inicialização e chamadas de ferramenta.
"""
import subprocess
import json
import sys
import os

class MCPClient:
    def __init__(self, command: list[str], cwd: str | None = None):
        self.command = command
        self.cwd = cwd
        self.process = None
        self.msg_id = 0
        self._start_server()

    def _start_server(self):
        """Inicia o subprocesso do servidor MCP."""
        sys.stderr.write(f"[mcp-client] Iniciando servidor MCP: {' '.join(self.command)}\n")
        
        # Garante que usamos o interpretador python correto se especificado
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=self.cwd
        )
        
        # Executa handshake inicial de handshake initialize
        init_res = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pipeline-orchestrator", "version": "1.0.0"}
        })
        
        # Envia notificação initialized opcional
        self._send_notification("notifications/initialized")
        sys.stderr.write("[mcp-client] Servidor MCP inicializado com sucesso!\n")

    def _next_id(self) -> int:
        self.msg_id += 1
        return self.msg_id

    def _send_request(self, method: str, params: dict) -> dict:
        """Envia requisição síncrona JSON-RPC e espera resposta."""
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": req_id
        }
        
        raw_msg = json.dumps(payload) + "\n"
        self.process.stdin.write(raw_msg)
        self.process.stdin.flush()
        
        # Lê a resposta do stdout (uma linha por JSON)
        line = self.process.stdout.readline()
        if not line:
            # Tenta ler do stderr para detalhar o erro
            stderr_err = self.process.stderr.read()
            raise RuntimeError(f"Servidor MCP fechou inesperadamente. Stderr: {stderr_err}")
            
        response = json.loads(line)
        if response.get("id") != req_id:
            raise ValueError(f"Resposta id incompatível. Esperado {req_id}, recebido {response.get('id')}")
            
        return response

    def _send_notification(self, method: str, params: dict | None = None) -> None:
        """Envia notificação unidirecional (sem esperar resposta)."""
        payload = {
            "jsonrpc": "2.0",
            "method": method
        }
        if params is not None:
            payload["params"] = params
            
        raw_msg = json.dumps(payload) + "\n"
        self.process.stdin.write(raw_msg)
        self.process.stdin.flush()

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Chama uma ferramenta específica no servidor MCP."""
        res = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        if "error" in res:
            raise RuntimeError(f"Erro na execução da tool '{tool_name}': {res['error'].get('message')}")
            
        content = res["result"].get("content", [])
        if not content:
            return ""
            
        # Retorna o texto do primeiro elemento de texto retornado
        for item in content:
            if item.get("type") == "text":
                return item.get("text", "")
        return ""

    def close(self):
        """Finaliza o subprocesso de forma limpa."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            sys.stderr.write("[mcp-client] Conexão com o servidor MCP encerrada.\n")
