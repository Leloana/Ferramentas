"""Skill registry with lazy loading.

A skill is a Python module inside this package that exposes:

    NAME = "plan"
    DESCRIPTION = "short one-line description shown in the index"
    KEYWORDS = ["plan", "design"]      # optional hints

    def run(args: str, ctx: dict) -> dict:
        '''Execute the skill. ctx contains: working_dir, model,
        wincli_content, conversation_history, session_log, state.'''
        ...

Only NAME and DESCRIPTION are loaded into the agent's context by default
(lazy index). The full module is imported only when the skill is actually
invoked.
"""

import importlib
import pkgutil
from pathlib import Path
from typing import Dict


_INDEX_CACHE = None
_LOADED = {}


def _scan():
    """Return {name: (description, module_name)} by reading top-of-file
    NAME/DESCRIPTION lines without importing the module."""
    pkg_dir = Path(__file__).parent
    out = {}
    for finder, mod_name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        if mod_name.startswith("_"):
            continue
        py = pkg_dir / f"{mod_name}.py"
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        name = None
        desc = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("NAME"):
                # NAME = "plan"
                _, _, rhs = line.partition("=")
                name = rhs.strip().strip('"').strip("'")
            elif line.startswith("DESCRIPTION"):
                _, _, rhs = line.partition("=")
                desc = rhs.strip().strip('"').strip("'")
            if name and desc:
                break
        if name:
            out[name] = (desc or "", mod_name)
    return out


def index() -> Dict[str, str]:
    """Returns {skill_name: description}. Cached."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        _INDEX_CACHE = _scan()
    return {n: d for n, (d, _) in _INDEX_CACHE.items()}


def invalidate():
    global _INDEX_CACHE
    _INDEX_CACHE = None


def load(name: str):
    """Import and return the skill module. Cached."""
    if name in _LOADED:
        return _LOADED[name]
    if _INDEX_CACHE is None:
        index()
    if name not in _INDEX_CACHE:
        return None
    _, mod_name = _INDEX_CACHE[name]
    mod = importlib.import_module(f"skills.{mod_name}")
    _LOADED[name] = mod
    return mod


def run(name: str, args: str, ctx: dict):
    mod = load(name)
    if mod is None:
        return {"error": f"unknown skill: {name}"}
    if not hasattr(mod, "run"):
        return {"error": f"skill {name} has no run() function"}
    return mod.run(args, ctx)
