"""
Servidor MCP ReadOnly.
Expõe ferramentas de leitura/inspeção do filesystem via stdio JSON-RPC (MCP).

Tools:
  - read_file        : conteúdo completo de um arquivo
  - read_many_files  : conteúdo de múltiplos arquivos numa só chamada
  - list_directory   : listagem (opcionalmente recursiva) de um diretório
  - search_text      : busca por regex em arquivos (grep-like)
  - file_exists      : verifica existência e tipo (file/dir)
  - file_stat        : tamanho, mtime, contagem de linhas
"""
import sys
import json
import os
import re
import fnmatch
from datetime import datetime


def _abs(path: str) -> str:
    return path if os.path.isabs(path) else os.path.abspath(path)


# ----- tools ------------------------------------------------------------

def read_file(path: str) -> str:
    p = _abs(path)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Arquivo não encontrado: {p}")
    if os.path.isdir(p):
        raise IsADirectoryError(f"Caminho é um diretório: {p}")
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def read_many_files(paths: list[str]) -> str:
    """Retorna JSON serializado: {path: content_or_error}."""
    out = {}
    for raw in paths:
        try:
            out[raw] = {"ok": True, "content": read_file(raw)}
        except Exception as e:
            out[raw] = {"ok": False, "error": str(e)}
    return json.dumps(out)


def list_directory(path: str, recursive: bool = False, max_depth: int = 3,
                   include_hidden: bool = False, glob: str | None = None) -> str:
    """Lista arquivos/diretórios. Retorna JSON com lista de entradas."""
    p = _abs(path)
    if not os.path.isdir(p):
        raise NotADirectoryError(f"Não é diretório: {p}")

    skip = {".git", "__pycache__", ".venv", "node_modules", ".srclight", "runs"}
    entries: list[dict] = []
    base_depth = p.count(os.sep)

    for root, dirs, files in os.walk(p):
        if not include_hidden:
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip]
        else:
            dirs[:] = [d for d in dirs if d not in skip]

        depth = root.count(os.sep) - base_depth
        if depth > max_depth:
            dirs[:] = []
            continue

        for name in dirs:
            full = os.path.join(root, name)
            entries.append({
                "path": os.path.relpath(full, p).replace("\\", "/"),
                "kind": "dir",
            })
        for name in files:
            if not include_hidden and name.startswith("."):
                continue
            if glob and not fnmatch.fnmatch(name, glob):
                continue
            full = os.path.join(root, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            entries.append({
                "path": os.path.relpath(full, p).replace("\\", "/"),
                "kind": "file",
                "size": size,
            })

        if not recursive:
            break

    return json.dumps({"root": p, "count": len(entries), "entries": entries})


def search_text(pattern: str, path: str = ".", glob: str = "*",
                max_results: int = 200, ignore_case: bool = True) -> str:
    """Grep recursivo por regex. Retorna JSON com matches (path:line:content)."""
    root = _abs(path)
    if not os.path.exists(root):
        raise FileNotFoundError(f"Path não encontrado: {root}")

    flags = re.IGNORECASE if ignore_case else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Regex inválida: {e}")

    skip_dirs = {".git", "__pycache__", ".venv", "node_modules", ".srclight", "runs"}
    matches: list[dict] = []

    targets: list[str]
    if os.path.isfile(root):
        targets = [root]
        walk_root = os.path.dirname(root)
    else:
        targets = []
        walk_root = root
        for r, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for f in files:
                if fnmatch.fnmatch(f, glob):
                    targets.append(os.path.join(r, f))

    for fp in targets:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if rx.search(line):
                        matches.append({
                            "path": os.path.relpath(fp, walk_root).replace("\\", "/"),
                            "line": lineno,
                            "text": line.rstrip("\n")[:400],
                        })
                        if len(matches) >= max_results:
                            return json.dumps({
                                "truncated": True, "count": len(matches), "matches": matches,
                            })
        except OSError:
            continue

    return json.dumps({"truncated": False, "count": len(matches), "matches": matches})


def file_exists(path: str) -> str:
    p = _abs(path)
    if not os.path.exists(p):
        return json.dumps({"exists": False})
    return json.dumps({
        "exists": True,
        "kind": "dir" if os.path.isdir(p) else "file",
        "path": p,
    })


def file_stat(path: str) -> str:
    p = _abs(path)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Não encontrado: {p}")
    st = os.stat(p)
    info = {
        "path": p,
        "kind": "dir" if os.path.isdir(p) else "file",
        "size_bytes": st.st_size,
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
    }
    if os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                info["line_count"] = sum(1 for _ in f)
        except OSError:
            info["line_count"] = None
    return json.dumps(info)


# ----- MCP plumbing -----------------------------------------------------

TOOLS = {
    "read_file": {
        "fn": lambda a: read_file(a["path"]),
        "spec": {
            "name": "read_file",
            "description": "Reads the entire content of a file.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    "read_many_files": {
        "fn": lambda a: read_many_files(a["paths"]),
        "spec": {
            "name": "read_many_files",
            "description": "Reads multiple files in one call. Returns a JSON object mapping each input path to {ok, content} or {ok:false, error}.",
            "inputSchema": {
                "type": "object",
                "properties": {"paths": {"type": "array", "items": {"type": "string"}}},
                "required": ["paths"],
            },
        },
    },
    "list_directory": {
        "fn": lambda a: list_directory(
            a["path"],
            recursive=a.get("recursive", False),
            max_depth=a.get("max_depth", 3),
            include_hidden=a.get("include_hidden", False),
            glob=a.get("glob"),
        ),
        "spec": {
            "name": "list_directory",
            "description": "Lists files and subdirectories of a path. Skips .git, __pycache__, .venv, node_modules, .srclight, runs by default. Returns JSON {root, count, entries:[{path, kind, size?}]}.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "recursive": {"type": "boolean", "default": False},
                    "max_depth": {"type": "integer", "default": 3},
                    "include_hidden": {"type": "boolean", "default": False},
                    "glob": {"type": "string", "description": "Optional fnmatch pattern for file names, e.g. '*.py'"},
                },
                "required": ["path"],
            },
        },
    },
    "search_text": {
        "fn": lambda a: search_text(
            a["pattern"],
            path=a.get("path", "."),
            glob=a.get("glob", "*"),
            max_results=a.get("max_results", 200),
            ignore_case=a.get("ignore_case", True),
        ),
        "spec": {
            "name": "search_text",
            "description": "Recursive regex search across files (grep-like). Returns JSON with matches: [{path, line, text}].",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern (Python re syntax)."},
                    "path": {"type": "string", "default": "."},
                    "glob": {"type": "string", "default": "*", "description": "fnmatch pattern restricting file names."},
                    "max_results": {"type": "integer", "default": 200},
                    "ignore_case": {"type": "boolean", "default": True},
                },
                "required": ["pattern"],
            },
        },
    },
    "file_exists": {
        "fn": lambda a: file_exists(a["path"]),
        "spec": {
            "name": "file_exists",
            "description": "Checks if a path exists. Returns JSON {exists, kind?}.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    "file_stat": {
        "fn": lambda a: file_stat(a["path"]),
        "spec": {
            "name": "file_stat",
            "description": "Returns metadata for a file/dir: size_bytes, modified, line_count (files only).",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
}


def _response(req_id, result=None, error=None):
    resp = {"jsonrpc": "2.0", "id": req_id}
    if error is not None:
        resp["error"] = error
    else:
        resp["result"] = result
    return resp


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
            if req_id is None:
                continue

            if method == "initialize":
                response = _response(req_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "serverInfo": {"name": "readonly-server", "version": "1.1.0"},
                })
            elif method == "tools/list":
                response = _response(req_id, {"tools": [t["spec"] for t in TOOLS.values()]})
            elif method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {}) or {}
                tool = TOOLS.get(name)
                if not tool:
                    response = _response(req_id, error={
                        "code": -32601,
                        "message": f"Tool '{name}' não encontrada no servidor ReadOnly.",
                    })
                else:
                    try:
                        text = tool["fn"](args)
                        response = _response(req_id, {"content": [{"type": "text", "text": text}]})
                    except Exception as e:
                        response = _response(req_id, error={"code": -32000, "message": str(e)})
            else:
                response = _response(req_id, {})

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            sys.stderr.write(f"readonly-server error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
