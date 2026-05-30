"""Core tools available to the agent.

Three patch_file variants are provided. Switch the active one by editing
ACTIVE_PATCH below. The public `patch_file` symbol always points to the
chosen variant so the agent loop doesn't need to know.

Errors from every tool are returned as {"error": "...", "hint": "..."} so
the model gets actionable feedback instead of bare exceptions.

BACKGROUND PROCESS POLICY:
run_command ALWAYS launches processes in the background (non-blocking).
All spawned processes are tracked in _BACKGROUND_PROCESSES and automatically
killed when wincli exits via atexit.
"""

import atexit
import difflib
import os
import subprocess
from pathlib2 import Path


# ── Background process tracking ────────────────────────────────────────
# Every process launched by run_command is registered here so it can be
# killed when wincli exits.  Key = PID, value = Popen object.
_BACKGROUND_PROCESSES: dict = {}


def cleanup_background_processes():
    """Kill every tracked background process (entire tree, forced).

    Called automatically via atexit when wincli exits.  Safe to call
    multiple times — already-dead PIDs are silently skipped.
    """
    for pid, proc in list(_BACKGROUND_PROCESSES.items()):
        try:
            subprocess.call(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
    _BACKGROUND_PROCESSES.clear()


atexit.register(cleanup_background_processes)

# ── ────────────────────────────────────────────────────────────────────

# Working directory — set from main.py via set_working_dir() so all tools
# resolve relative paths against the project root, not the OS CWD.
_WORKING_DIR = None  # Path | None


def set_working_dir(wd):
    """Called once from main.py to capture the project root as an absolute
    Path. Every tool that resolves paths uses this instead of Path.cwd()."""
    global _WORKING_DIR
    from pathlib import Path
    _WORKING_DIR = Path(wd).resolve()


ACTIVE_PATCH = "v3"  # "v1" | "v2" | "v3" — v3 (line-range) is most robust for small models

# Paths the AI agent must never touch — its own config and session data.
_GUARDED_DIRS = [".persist"]


def _resolve_abs(raw: str) -> str:
    """Return an absolute path string, resolving relative paths against
    the project working_dir (set via set_working_dir). Falls back to CWD
    if the working_dir hasn't been set yet."""
    p = Path(raw)
    if not p.is_absolute():
        base = _WORKING_DIR if _WORKING_DIR is not None else Path.cwd()
        p = base / p
    return str(p.resolve())


def _guard_path(raw, label="path"):
    """Return an error dict if `raw` enters a guarded directory."""
    if not raw:
        return None
    parts = Path(raw).parts
    for g in _GUARDED_DIRS:
        if g in parts:
            return _err(f"{label} enters guarded directory '{g}'",
                        "this directory contains session/config data — use a different path")
    return None


def _err(message, hint=None):
    out = {"error": message}
    if hint:
        out["hint"] = hint
    return out


READ_FILE_MAX_LINES = 300
RUN_COMMAND_MAX_LINES = 100


def _truncate_lines(text, max_lines, label):
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text, False
    keep = max_lines // 2
    head = lines[:keep]
    tail = lines[-keep:]
    omitted = len(lines) - 2 * keep
    middle = f"[... {omitted} lines of {label} omitted ...]"
    return "\n".join(head + [middle] + tail), True


def run_command(args):
    """Launch a Windows PowerShell command in the background (non-blocking).

    The process starts immediately and control returns to the agent without
    waiting for completion.  All spawned processes are tracked in
    _BACKGROUND_PROCESSES and killed automatically when wincli exits.

    The agent receives the PID so it can monitor or interact with the
    process via subsequent commands (e.g. ``Get-Process -Id <PID>``).

    Because stdout/stderr are discarded (the process runs detached), this
    tool is NOT suitable for commands whose output the agent needs to
    inspect.  Use it for servers, watchers, long-running tasks.
    """
    command = args.get("command")
    if not command:
        return _err("missing 'command' arg")
    try:
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        _BACKGROUND_PROCESSES[proc.pid] = proc
        return {
            "status": "started",
            "pid": proc.pid,
            "message": f"command launched in background (PID {proc.pid}). "
                       f"It will be terminated when wincli exits.",
        }
    except FileNotFoundError:
        return _err("powershell.exe not found", "are you running on Windows?")


def read_file(args):
    """Read a file. Optional `offset` (1-indexed line) and `limit` (max
    lines). Without them, caps at READ_FILE_MAX_LINES with head+tail.

    Args:
        path: file path (required)
        offset: starting line (1-indexed, optional)
        limit: max lines to return (optional)
    """
    raw = args.get("path")
    if not raw:
        return _err("missing 'path' arg")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    path = Path(raw)
    if not path.exists():
        return _err(f"file not found: {raw}", _suggest_path(raw))
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _err(f"file is not utf-8 text: {raw}", "is this a binary file?")
    except Exception as e:
        return _err(f"could not read {raw}: {e}")

    all_lines = content.splitlines()
    total = len(all_lines)
    offset = args.get("offset")
    limit = args.get("limit")

    if offset is not None or limit is not None:
        try:
            o = int(offset) if offset is not None else 1
            l = int(limit) if limit is not None else READ_FILE_MAX_LINES
        except (TypeError, ValueError):
            return _err("offset/limit must be integers")
        if o < 1:
            o = 1
        slice_ = all_lines[o - 1:o - 1 + l]
        numbered = "\n".join(f"{o + i:>4}: {line}" for i, line in enumerate(slice_))
        return {"numbered": numbered, "lines_returned": len(slice_),
                "lines_total": total, "offset": o, "limit": l,
                "content": "\n".join(slice_)}

    if total <= READ_FILE_MAX_LINES:
        numbered = "\n".join(f"{i+1:>4}: {line}" for i, line in enumerate(all_lines))
        return {"content": content, "numbered": numbered, "lines": total}

    # Default truncation: head + tail
    keep = READ_FILE_MAX_LINES // 2
    head = all_lines[:keep]
    tail = all_lines[-keep:]
    omitted = total - 2 * keep
    head_n = "\n".join(f"{i+1:>4}: {line}" for i, line in enumerate(head))
    tail_start = total - keep + 1
    tail_n = "\n".join(f"{tail_start + i:>4}: {line}" for i, line in enumerate(tail))
    notice = (f"\n[... lines {keep+1}..{total-keep} ({omitted}) omitted — "
              f"call read_file again with offset/limit to see them ...]\n")
    return {"numbered": head_n + notice + tail_n, "lines": total,
            "truncated": True, "shown": f"1..{keep} + {tail_start}..{total}"}


def write_file(args):
    """Write or overwrite a file with given content."""
    raw = args.get("path")
    if not raw:
        return _err("missing 'path' arg")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    if "content" not in args:
        return _err("missing 'content' arg")
    path = Path(raw)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
    except Exception as e:
        return _err(f"could not write {raw}: {e}")
    return {"status": "ok", "path": raw}


def append_file(args):
    """Append text to the end of a file, creating it if missing.

    Built for segmenting large files: a write_file task creates the file with
    its first section, then append_file tasks add each remaining chunk. Every
    call carries only a small slice of content, so the tool-call JSON stays
    well-formed even when the finished file is large.

    Args:
        path:    file path (required)
        content: text to append (required)
    """
    raw = args.get("path")
    if not raw:
        return _err("missing 'path' arg")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    if "content" not in args:
        return _err("missing 'content' arg")
    path = Path(raw)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(raw, "a", encoding="utf-8") as f:
            f.write(args["content"])
    except Exception as e:
        return _err(f"could not append to {raw}: {e}")
    return {"status": "appended", "path": raw}


# ---------- patch variants ----------
def patch_file_v1(args):
    raw = args.get("path")
    old = args.get("old_str")
    new = args.get("new_str")
    if not raw or old is None or new is None:
        return _err("required args: path, old_str, new_str")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    path = Path(raw)
    if not path.exists():
        return _err(f"file not found: {raw}")
    try:
        original_bytes = path.read_bytes()
        content_raw = original_bytes.decode("utf-8")
    except Exception as e:
        return _err(f"could not read {raw}: {e}")

    # Normaliza para LF para comparação e substituição
    content_norm = content_raw.replace("\r\n", "\n")
    old_norm = old.replace("\r\n", "\n")
    new_norm = new.replace("\r\n", "\n")

    if old_norm not in content_norm:
        return _err(
            f"old_str not found in {raw}",
            _fuzzy_hint(content_norm, old_norm),
        )
    count = content_norm.count(old_norm)
    if count > 1:
        return _err(
            f"old_str matches {count} times in {raw} (ambiguous)",
            "add more surrounding context to make old_str unique",
        )

    patched_norm = content_norm.replace(old_norm, new_norm, 1)

    # Re-aplica o line ending original do arquivo
    eol = "\r\n" if "\r\n" in content_raw else "\n"
    patched_final = patched_norm.replace("\n", eol)

    path.write_bytes(patched_final.encode("utf-8"))
    return {"status": "patched", "path": raw, "variant": "v1"}


def patch_file_v2(args):
    """Variant 2: anchor-based.

    Requires `path`, `old_str`, plus optional `context_before` and
    `context_after` that bracket old_str in the file. This kills whitespace
    ambiguity because anchors don't need to match indentation exactly — they
    just need to appear in order around old_str.
    """
    raw = args.get("path")
    old = args.get("old_str")
    new = args.get("new_str")
    before = args.get("context_before", "")
    after = args.get("context_after", "")
    if not raw or old is None or new is None:
        return _err("required args: path, old_str, new_str (+ optional context_before/after)")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    path = Path(raw)
    if not path.exists():
        return _err(f"file not found: {raw}")
    content = path.read_text(encoding="utf-8")

    # Find all occurrences of old_str
    occurrences = []
    start = 0
    while True:
        idx = content.find(old, start)
        if idx == -1:
            break
        occurrences.append(idx)
        start = idx + 1

    if not occurrences:
        return _err(
            f"old_str not found in {raw}",
            _fuzzy_hint(content, old),
        )

    # If anchors provided, filter by them
    if before or after:
        filtered = []
        for idx in occurrences:
            window_start = max(0, idx - 400)
            window_end = min(len(content), idx + len(old) + 400)
            window = content[window_start:window_end]
            if (not before or before in window[:idx - window_start]) and \
               (not after or after in window[idx - window_start + len(old):]):
                filtered.append(idx)
        occurrences = filtered

    if not occurrences:
        return _err(
            "old_str found but anchors didn't match",
            "context_before/context_after must appear around old_str in the file",
        )
    if len(occurrences) > 1:
        return _err(
            f"still {len(occurrences)} matches after anchors",
            "tighten context_before/context_after",
        )

    idx = occurrences[0]
    patched = content[:idx] + new + content[idx + len(old):]
    path.write_text(patched, encoding="utf-8")
    return {"status": "patched", "path": raw, "variant": "v2"}


def patch_file_v3(args):
    """Variant 3: line-range replacement.

    Requires `path`, `start_line`, `end_line` (1-indexed, inclusive), and
    `new_content`. No string matching — the model just points at line
    numbers (which it has from read_file's 'numbered' output).
    """
    raw = args.get("path")
    start_line = args.get("start_line")
    end_line = args.get("end_line")
    new_content = args.get("new_content")
    if not raw or start_line is None or end_line is None or new_content is None:
        return _err("required args: path, start_line, end_line, new_content")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    path = Path(raw)
    if not path.exists():
        return _err(f"file not found: {raw}")
    try:
        start_line = int(start_line)
        end_line = int(end_line)
    except (TypeError, ValueError):
        return _err("start_line/end_line must be integers")

    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    n = len(lines)
    if start_line < 1 or end_line > n or start_line > end_line:
        return _err(
            f"invalid range {start_line}-{end_line} for file with {n} lines",
            "use read_file first to see line numbers",
        )
    # Ensure new_content ends with newline if replacing non-final lines
    if not new_content.endswith("\n") and end_line < n:
        new_content += "\n"
    patched = "".join(lines[:start_line - 1]) + new_content + "".join(lines[end_line:])
    path.write_text(patched, encoding="utf-8")
    return {"status": "patched", "path": raw, "variant": "v3",
            "replaced_lines": f"{start_line}-{end_line}"}


_VARIANTS = {"v1": patch_file_v1, "v2": patch_file_v2, "v3": patch_file_v3}


def patch_file(args):
    """Active patch implementation (configurable via ACTIVE_PATCH)."""
    impl = _VARIANTS.get(ACTIVE_PATCH, patch_file_v1)
    return impl(args)


# ---------- discovery / search ----------

def list_dir(args):
    raw = args.get("path", str(_WORKING_DIR) if _WORKING_DIR is not None else ".")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    path = Path(raw)
    if not path.exists():
        return _err(f"directory not found: {raw}")
    if not path.is_dir():
        return _err(f"not a directory: {raw}")
    try:
        entries = sorted(os.listdir(raw))
    except Exception as e:
        return _err(f"could not list {raw}: {e}")
    # Mark dirs with trailing slash so the model knows
    decorated = []
    for e in entries:
        p = path / e
        if any(g in Path(p).parts for g in _GUARDED_DIRS):
            continue
        decorated.append(e + "/" if p.is_dir() else e)
    return {"entries": decorated}


def search_file(args):
    raw = args.get("path")
    query = args.get("query")
    if not raw or query is None:
        return _err("required args: path, query")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    path = Path(raw)
    if not path.exists():
        parent = path.parent
        if parent.exists():
            try:
                entries = sorted(os.listdir(str(parent)))
                decorated = []
                for e in entries:
                    p = parent / e
                    decorated.append(e + "/" if p.is_dir() else e)
                hint = (
                    f"file not found: {raw}\n"
                    f"available in {parent}:\n"
                    + "\n".join(f"  {e}" for e in decorated)
                )
                close = difflib.get_close_matches(
                    path.name, [e.rstrip("/") for e in decorated], n=5, cutoff=0.3
                )
                if close:
                    hint += "\ndid you mean: " + ", ".join(close)
                return _err("file not found", hint)
            except Exception:
                pass
        return _err(f"file not found: {raw}")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        return _err(f"could not read {raw}: {e}")
    matches = []
    for i, line in enumerate(text.splitlines(), start=1):
        if query in line:
            matches.append({"line": i, "content": line})
    return {"matches": matches}


def remove_file(args):
    """Remove a file or directory using PowerShell Remove-Item.

    Args:
        path      : absolute path to file or directory (required)
        recursive : true to remove a non-empty directory tree (optional, default false)
    """
    raw = args.get("path")
    if not raw:
        return _err("missing 'path' arg")
    raw = _resolve_abs(raw)
    if g := _guard_path(raw):
        return g
    path = Path(raw)
    if not path.exists():
        return _err(f"path not found: {raw}", "check spelling or use list_dir to verify")

    recursive = str(args.get("recursive", "false")).lower() in ("true", "1", "yes")

    if path.is_dir() and not recursive:
        return _err(
            f"'{raw}' is a directory",
            "pass recursive: true to remove a directory and its contents",
        )

    ps_flags = "-Recurse -Force" if path.is_dir() else "-Force"
    cmd = f"Remove-Item -LiteralPath '{raw}' {ps_flags}"
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return _err("powershell.exe not found", "are you running on Windows?")
    except subprocess.TimeoutExpired:
        return _err("remove_file timed out after 30s")

    if result.returncode != 0:
        return _err(
            f"Remove-Item failed (rc={result.returncode})",
            (result.stderr or result.stdout or "").strip()[:400],
        )
    return {"status": "removed", "path": raw}


def http_get(args):
    import requests
    url = args.get("url")
    if not url:
        return _err("missing 'url' arg")
    try:
        response = requests.get(url, timeout=10)
    except Exception as e:
        return _err(f"http_get failed: {e}")
    return {"body": response.text[:3000], "status_code": response.status_code}


# ---------- helpers ----------

def _fuzzy_hint(content, old):
    """Return a hint with the 3 closest line matches to old_str's first line."""
    if not old:
        return None
    first_line = old.splitlines()[0] if "\n" in old else old
    candidates = content.splitlines()
    close = difflib.get_close_matches(first_line, candidates, n=3, cutoff=0.5)
    if not close:
        return "no similar lines found — check the file path and re-read the file"
    return "did you mean one of these lines?\n" + "\n".join(f"  • {c}" for c in close)


def _suggest_path(raw):
    """Suggest existing files when a path doesn't exist."""
    try:
        parent = Path(raw).parent
        if not parent.exists():
            abs_parent = _resolve_abs(raw) if not Path(raw).is_absolute() else raw
            parent = Path(abs_parent).parent
            if not parent.exists():
                return None
        siblings = [e for e in os.listdir(str(parent)) if not e.startswith(".")]
        target = Path(raw).name
        close = difflib.get_close_matches(target, siblings, n=3, cutoff=0.5)
        if close:
            return "did you mean: " + ", ".join(close)
    except Exception:
        pass
    return None


# Tool registry — used by skills system to know what's "core".
CORE_TOOLS = {
    "run_command": run_command,
    "read_file": read_file,
    "write_file": write_file,
    "append_file": append_file,
    "patch_file": patch_file,
    "remove_file": remove_file,
    "list_dir": list_dir,
    "search_file": search_file,
    "http_get": http_get,
}
