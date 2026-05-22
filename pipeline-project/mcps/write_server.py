"""
Servidor MCP Write.
Expõe as ferramentas `write_file` e `apply_patch` usando o protocolo stdio JSON-RPC do Model Context Protocol (MCP).
"""
import sys
import json
import os
import subprocess
import difflib

def apply_patch_tolerant(file_content: str, patch_str: str) -> str:
    original_lines = file_content.splitlines(keepends=True)
    patch_lines = patch_str.splitlines()
    
    hunks = []
    current_hunk = None
    
    # Parse hunks
    for line in patch_lines:
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            # Parse header, e.g., @@ -1,4 +1,4 @@
            parts = line.split()
            old_start = 1
            if len(parts) >= 2:
                old_info = parts[1] # e.g. "-1,4"
                if old_info.startswith("-"):
                    old_info = old_info[1:]
                if "," in old_info:
                    old_start = int(old_info.split(",")[0])
                else:
                    try:
                        old_start = int(old_info)
                    except ValueError:
                        old_start = 1
            if current_hunk:
                hunks.append(current_hunk)
            current_hunk = {"old_start": old_start, "lines": []}
        elif current_hunk is not None:
            current_hunk["lines"].append(line)
            
    if current_hunk:
        hunks.append(current_hunk)
        
    if not hunks:
        return file_content
        
    offset = 0
    new_lines = list(original_lines)
    
    for hunk in hunks:
        old_start = hunk["old_start"]
        hunk_lines = hunk["lines"]
        
        # Split hunk lines into original_match_lines and replacement_lines
        original_match_lines = []
        replacement_lines = []
        for hl in hunk_lines:
            if hl.startswith("-"):
                original_match_lines.append(hl[1:])
            elif hl.startswith("+"):
                replacement_lines.append(hl[1:])
            elif hl.startswith(" "):
                original_match_lines.append(hl[1:])
                replacement_lines.append(hl[1:])
            else:
                # No prefix, treat as context (sometimes models forget the leading space)
                original_match_lines.append(hl)
                replacement_lines.append(hl)
                
        # Find match in new_lines
        match_idx = -1
        expected_idx = max(0, min(old_start - 1 + offset, len(new_lines)))
        
        # If original_match_lines is empty, we just insert at expected_idx
        if not original_match_lines:
            match_idx = expected_idx
            replacement_lines_with_nl = [r + "\n" if not r.endswith("\n") else r for r in replacement_lines]
            new_lines[match_idx:match_idx] = replacement_lines_with_nl
            offset += len(replacement_lines_with_nl)
            continue
            
        def lines_match(file_slice, pattern):
            if len(file_slice) != len(pattern):
                return False
            for fl, pl in zip(file_slice, pattern):
                if fl.rstrip("\r\n") != pl.rstrip("\r\n"):
                    return False
            return True
            
        search_range = range(0, len(new_lines) - len(original_match_lines) + 1)
        search_range = sorted(search_range, key=lambda x: abs(x - expected_idx))
        
        for idx in search_range:
            slice_lines = new_lines[idx:idx+len(original_match_lines)]
            if lines_match(slice_lines, original_match_lines):
                match_idx = idx
                break
                
        if match_idx == -1:
            def lines_match_fuzzy(file_slice, pattern):
                if len(file_slice) != len(pattern):
                    return False
                for fl, pl in zip(file_slice, pattern):
                    if "".join(fl.split()) != "".join(pl.split()):
                        return False
                return True
            for idx in search_range:
                slice_lines = new_lines[idx:idx+len(original_match_lines)]
                if lines_match_fuzzy(slice_lines, original_match_lines):
                    match_idx = idx
                    break
                    
        if match_idx != -1:
            replacement_lines_with_nl = []
            for r in replacement_lines:
                if not r.endswith("\n"):
                    replacement_lines_with_nl.append(r + "\n")
                else:
                    replacement_lines_with_nl.append(r)
            
            new_lines[match_idx:match_idx+len(original_match_lines)] = replacement_lines_with_nl
            offset += len(replacement_lines_with_nl) - len(original_match_lines)
        else:
            raise ValueError(f"Nao foi possivel encontrar o contexto do patch no arquivo. Linhas esperadas:\n" + "\n".join(original_match_lines))
            
    return "".join(new_lines)

def find_git_root(start_path: str) -> str:
    current = os.path.abspath(start_path)
    if os.path.isfile(current):
        current = os.path.dirname(current)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.getcwd()

def generate_git_diff(file_path: str, original_content: str, new_content: str, git_root: str) -> str:
    original_lines = original_content.splitlines()
    new_lines = new_content.splitlines()
    
    # Resolve file path relative to git root for git apply compatibility
    # Path inside diff must use forward slashes
    rel_path = os.path.relpath(file_path, git_root).replace("\\", "/")
    
    diff_lines = list(difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{rel_path}",
        tofile=f"b/{rel_path}",
        lineterm="\n"
    ))
    return "".join(diff_lines)

def write_file(path: str, content: str) -> str:
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Arquivo gravado com sucesso em {path}"

def apply_patch(path: str, unified_diff: str) -> str:
    if not os.path.isabs(path):
        path = os.path.abspath(path)
    
    if "\n" not in unified_diff and any(m in unified_diff for m in ["@@", "---", "+++"]):
        for marker in ["--- ", "+++ ", "@@ ", "\n+"]:
            unified_diff = unified_diff.replace(marker, "\n" + marker)
        # Garante que linhas +/- que ficaram grudadas também sejam separadas
        import re
        unified_diff = re.sub(r'(?<!\n)([\+\- ](?=[^\+\- \n]))', r'\n\1', unified_diff)
        unified_diff = unified_diff.lstrip("\n")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Arquivo para patch nao encontrado: {path}")
        
    with open(path, "r", encoding="utf-8") as f:
        original_content = f.read()
        
    # 1. Aplica o patch tolerante na memoria
    new_content = apply_patch_tolerant(original_content, unified_diff)
    
    # 2. Gera diff limpo/perfeito
    git_root = find_git_root(path)
    clean_diff = generate_git_diff(path, original_content, new_content, git_root)
    
    # Se nao houver diferencas, retorna sucesso diretamente
    if not clean_diff.strip():
        return f"Sem alteracoes a serem aplicadas no arquivo {path}"
        
    # 3. Executa git apply --check - no git_root
    try:
        subprocess.run(
            ["git", "apply", "--check", "-"],
            input=clean_diff,
            text=True,
            capture_output=True,
            cwd=git_root,
            check=True
        )
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.strip() if e.stderr else str(e)
        raise RuntimeError(f"git apply --check falhou:\n{stderr_msg}\nDiff gerado:\n{clean_diff}")
        
    # 4. Grava o novo conteudo
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    return f"Patch aplicado e validado com sucesso via git apply em {path}"

# ----- Tools adicionais -------------------------------------------------

# Diretórios proibidos para qualquer mutação (delete/move). path absoluto resolvido
# precisa ficar dentro do git root, e fora destes nomes.
_FORBIDDEN_SEGMENTS = {".git", ".srclight", ".venv", "node_modules"}


def _safety_check(path: str) -> str:
    """Resolve path absoluto e bloqueia traversal/segmentos proibidos."""
    abs_path = path if os.path.isabs(path) else os.path.abspath(path)
    parts = os.path.normpath(abs_path).split(os.sep)
    for seg in parts:
        if seg in _FORBIDDEN_SEGMENTS:
            raise PermissionError(f"Segmento proibido no path: {seg}")
    git_root = find_git_root(abs_path)
    if not abs_path.startswith(os.path.abspath(git_root)):
        raise PermissionError(f"Path fora do git root: {abs_path}")
    return abs_path


def create_directory(path: str) -> str:
    p = _safety_check(path)
    os.makedirs(p, exist_ok=True)
    return f"Diretório garantido: {p}"


def delete_file(path: str) -> str:
    p = _safety_check(path)
    if not os.path.exists(p):
        raise FileNotFoundError(f"Arquivo não encontrado para deletar: {p}")
    if os.path.isdir(p):
        raise IsADirectoryError(f"delete_file não remove diretórios. Use delete_directory: {p}")
    os.remove(p)
    return f"Arquivo removido: {p}"


def move_file(src: str, dest: str) -> str:
    s = _safety_check(src)
    d = _safety_check(dest)
    if not os.path.exists(s):
        raise FileNotFoundError(f"Origem não existe: {s}")
    if os.path.exists(d):
        raise FileExistsError(f"Destino já existe: {d}")
    os.makedirs(os.path.dirname(d), exist_ok=True)
    os.rename(s, d)
    return f"Movido {s} -> {d}"


def append_to_file(path: str, content: str) -> str:
    p = _safety_check(path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(content)
    return f"Append concluído em {p} ({len(content)} chars)"


# ----- MCP plumbing -----------------------------------------------------

TOOLS = {
    "write_file": {
        "fn": lambda a: write_file(a["path"], a["content"]),
        "spec": {
            "name": "write_file",
            "description": "Writes the entire content to a file, creating directories as needed.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    "apply_patch": {
        "fn": lambda a: apply_patch(a["path"], a["unified_diff"]),
        "spec": {
            "name": "apply_patch",
            "description": "Applies a unified diff to a file, validating via 'git apply --check' before writing.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "unified_diff": {"type": "string"},
                },
                "required": ["path", "unified_diff"],
            },
        },
    },
    "create_directory": {
        "fn": lambda a: create_directory(a["path"]),
        "spec": {
            "name": "create_directory",
            "description": "Creates a directory (and parents) if missing. Idempotent.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    "delete_file": {
        "fn": lambda a: delete_file(a["path"]),
        "spec": {
            "name": "delete_file",
            "description": "Removes a single file. Refuses directories and paths outside the git root or under .git/.venv/.srclight/node_modules.",
            "inputSchema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    "move_file": {
        "fn": lambda a: move_file(a["src"], a["dest"]),
        "spec": {
            "name": "move_file",
            "description": "Renames or moves a file. Fails if destination already exists.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "src": {"type": "string"},
                    "dest": {"type": "string"},
                },
                "required": ["src", "dest"],
            },
        },
    },
    "append_to_file": {
        "fn": lambda a: append_to_file(a["path"], a["content"]),
        "spec": {
            "name": "append_to_file",
            "description": "Appends content to a file (creates if missing). Use for logs, incremental docs, or growing outputs.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
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
    sys.stderr.write("write-server: iniciado\n")
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
                    "serverInfo": {"name": "write-server", "version": "1.1.0"},
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
                        "message": f"Tool '{name}' não encontrada no servidor Write.",
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
            sys.stderr.write(f"write-server error: {e}\n")
            sys.stderr.flush()


if __name__ == "__main__":
    main()
