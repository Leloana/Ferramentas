"""Per-conversation JSON log written to .persist/<id>.json.

Schema:
{
  "session_id": str,
  "started_at": iso8601,
  "model": str,
  "turns": [
    {
      "user": str,
      "chain": [
        {
          "kind": "assistant" | "tool",
          "content": str,                 # assistant text or tool result
          "prompt_tokens": int,
          "gen_tokens": int,
          "elapsed_s": float,
          "tps": float,
          "tool_call": null | {"name": str, "args": dict},
          "tool_result": null | dict
        }
      ],
      "totals": {"prompt_tokens": int, "gen_tokens": int, "elapsed_s": float}
    }
  ],
  "session_totals": {"prompt_tokens": int, "gen_tokens": int, "elapsed_s": float}
}
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib2 import Path


class SessionLog:
    def __init__(self, working_dir: Path, model: str,
                 resumed_from: str = None):
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
        # Each session lives in its own sub-folder: .persist/<session_id>/
        self.dir = working_dir / ".persist" / self.session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "session.json"
        self.data = {
            "session_id": self.session_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "resumed_from": resumed_from,
            "turns": [],
            "session_totals": {"prompt_tokens": 0, "gen_tokens": 0, "elapsed_s": 0.0},
        }
        self._current_turn = None
        self._flush()

    def start_turn(self, user_input: str):
        self._current_turn = {
            "user": user_input,
            "chain": [],
            "totals": {"prompt_tokens": 0, "gen_tokens": 0, "elapsed_s": 0.0},
        }
        self.data["turns"].append(self._current_turn)

    def log_step(self, *, kind, content, prompt_tokens=0, gen_tokens=0,
                 elapsed_s=0.0, tool_call=None, tool_result=None):
        if self._current_turn is None:
            self.start_turn("")
        tps = gen_tokens / elapsed_s if elapsed_s > 0 else 0
        self._current_turn["chain"].append({
            "kind": kind,
            "content": content,
            "prompt_tokens": prompt_tokens,
            "gen_tokens": gen_tokens,
            "elapsed_s": elapsed_s,
            "tps": tps,
            "tool_call": tool_call,
            "tool_result": tool_result,
        })
        self._current_turn["totals"]["prompt_tokens"] += prompt_tokens
        self._current_turn["totals"]["gen_tokens"] += gen_tokens
        self._current_turn["totals"]["elapsed_s"] += elapsed_s
        st = self.data["session_totals"]
        st["prompt_tokens"] += prompt_tokens
        st["gen_tokens"] += gen_tokens
        st["elapsed_s"] += elapsed_s
        self._flush()

    def session_totals(self):
        return dict(self.data["session_totals"])

    def turn_count(self):
        return len(self.data["turns"])

    def _flush(self):
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except Exception:
            pass


def list_sessions(working_dir: Path, limit: int = 20):
    """List recent persisted sessions, newest first. Returns
    [{'id','model','turns','started_at','path','resumed_from'}]."""
    pdir = working_dir / ".persist"
    if not pdir.exists():
        return []
    # Each session is stored as .persist/<session_id>/session.json
    files = sorted(
        pdir.glob("*/session.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    out = []
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "id": data.get("session_id", p.parent.name),
                "model": data.get("model", "?"),
                "turns": len(data.get("turns", [])),
                "started_at": data.get("started_at", ""),
                "path": str(p),
                "resumed_from": data.get("resumed_from"),
            })
        except Exception:
            continue
    return out


def load_session(working_dir: Path, session_id_or_prefix: str):
    """Load a session by id prefix or 'last'. Returns the JSON dict or None."""
    pdir = working_dir / ".persist"
    if not pdir.exists():
        return None
    if session_id_or_prefix == "last":
        files = sorted(
            pdir.glob("*/session.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            return None
        return json.loads(files[0].read_text(encoding="utf-8"))
    # Match by prefix against the session folder name
    for p in pdir.glob("*/session.json"):
        if p.parent.name.startswith(session_id_or_prefix):
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def rebuild_history(session_data: dict, system_prompt: str):
    """Reconstruct the messages list for run_agent_loop from a loaded
    session. system_prompt is taken from the *current* session (in case
    WINCLI changed)."""
    messages = [{"role": "system", "content": system_prompt}]
    for turn in session_data.get("turns", []):
        # Each turn begins with the user input
        user_text = turn.get("user", "")
        if user_text and not user_text.startswith("/"):
            messages.append({"role": "user", "content": user_text})
        for step in turn.get("chain", []):
            content = step.get("content", "")
            tool_call = step.get("tool_call")
            tool_result = step.get("tool_result")
            if content:
                messages.append({"role": "assistant", "content": content})
            if tool_call and tool_result:
                from agent import format_tool_result
                messages.append({"role": "user",
                                 "content": format_tool_result(tool_result)})
    return messages
