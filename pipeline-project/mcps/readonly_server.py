"""
Servidor MCP ReadOnly.
Expõe a ferramenta `read_file` de forma síncrona usando o protocolo stdio JSON-RPC do Model Context Protocol (MCP).
"""
import sys
import json
import os

def read_file(path: str) -> str:
    """Lê o conteúdo completo de um arquivo."""
    # Resolve caminhos relativos ao diretório de trabalho se necessário
    if not os.path.isabs(path):
        path = os.path.abspath(path)
        
    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
        
    if os.path.isdir(path):
        raise IsADirectoryError(f"Caminho é um diretório, não um arquivo: {path}")
        
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def main():
    sys.stderr.write("readonly-server: iniciado\n")
    sys.stderr.flush()
    
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            method = request.get("method")
            req_id = request.get("id")
            
            if req_id is not None:
                if method == "initialize":
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "serverInfo": {"name": "readonly-server", "version": "1.0.0"}
                        }
                    }
                elif method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "tools": [
                                {
                                    "name": "read_file",
                                    "description": "Reads the entire content of a file at the specified absolute or relative path, returning the content as text.",
                                    "inputSchema": {
                                        "type": "object",
                                        "properties": {
                                            "path": {
                                                "type": "string",
                                                "description": "The absolute or relative path of the file to read."
                                            }
                                        },
                                        "required": ["path"]
                                    }
                                }
                            ]
                        }
                    }
                elif method == "tools/call":
                    params = request.get("params", {})
                    tool_name = params.get("name")
                    args = params.get("arguments", {})
                    
                    if tool_name == "read_file":
                        file_path = args.get("path")
                        try:
                            content = read_file(file_path)
                            response = {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": content
                                        }
                                    ]
                                }
                            }
                        except Exception as e:
                            response = {
                                "jsonrpc": "2.0",
                                "id": req_id,
                                "error": {
                                    "code": -32000,
                                    "message": str(e)
                                }
                            }
                    else:
                        response = {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "error": {
                                "code": -32601,
                                "message": f"Tool '{tool_name}' não encontrada no servidor ReadOnly."
                            }
                        }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {}
                    }
                    
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            
        except Exception as e:
            sys.stderr.write(f"readonly-server error: {e}\n")
            sys.stderr.flush()

if __name__ == "__main__":
    main()
