"""File snapshot / undo system.

Before any write_file or patch_file executes, take_snapshot() copies the
existing file to .persist/snapshots/<session>/<seq>/<path>. The undo
stack lets the user revert the most recent N edits.

Also tracks diff stats per session: which files were touched, the
earliest snapshot vs current state.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict


@dataclass
class SnapshotEntry:
    seq: int
    path: str              # original file path
    snapshot_path: str     # backup location (or empty if file was new)
    action: str            # 'write' or 'patch'
    existed_before: bool


class SnapshotManager:
    def __init__(self, working_dir: Path, session_id: str):
        self.working_dir = working_dir
        self.root = working_dir / ".persist" / "snapshots" / session_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.stack: List[SnapshotEntry] = []
        self.first_snapshot: Dict[str, str] = {}  # path → first snapshot location
        self._seq = 0

    def take(self, path: str, action: str) -> SnapshotEntry:
        self._seq += 1
        src = Path(path)
        existed = src.exists()
        snap_dir = self.root / str(self._seq)
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_path = snap_dir / src.name
        if existed:
            try:
                shutil.copy2(src, snap_path)
            except Exception:
                snap_path = Path("")  # snapshot failed; keep entry anyway
        entry = SnapshotEntry(
            seq=self._seq, path=path,
            snapshot_path=str(snap_path) if existed else "",
            action=action, existed_before=existed,
        )
        self.stack.append(entry)
        # Remember the earliest snapshot per path for diff stats
        if path not in self.first_snapshot:
            self.first_snapshot[path] = entry.snapshot_path if existed else ""
        return entry

    def undo_last(self, n: int = 1) -> List[SnapshotEntry]:
        """Pop and revert the last N entries. Returns the reverted ones
        (in order they were popped, i.e. most-recent-first)."""
        reverted = []
        for _ in range(n):
            if not self.stack:
                break
            entry = self.stack.pop()
            target = Path(entry.path)
            if entry.existed_before and entry.snapshot_path:
                try:
                    shutil.copy2(entry.snapshot_path, target)
                except Exception:
                    pass
            elif not entry.existed_before:
                # File was newly created — delete it
                try:
                    if target.exists():
                        target.unlink()
                except Exception:
                    pass
            reverted.append(entry)
        return reverted

    def diff_stats(self) -> List[Dict]:
        """For each file touched in this session, compare earliest
        snapshot to current contents and return +/- line counts."""
        stats = []
        for path, first_snap in self.first_snapshot.items():
            current = Path(path)
            try:
                cur_text = current.read_text(encoding="utf-8") if current.exists() else ""
            except Exception:
                cur_text = ""
            if first_snap:
                try:
                    old_text = Path(first_snap).read_text(encoding="utf-8")
                except Exception:
                    old_text = ""
            else:
                old_text = ""  # file was new
            old_lines = old_text.splitlines()
            cur_lines = cur_text.splitlines()
            import difflib
            added = removed = 0
            for line in difflib.unified_diff(old_lines, cur_lines, n=0):
                if line.startswith("+") and not line.startswith("+++"):
                    added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    removed += 1
            stats.append({
                "path": path, "added": added, "removed": removed,
                "was_new": not bool(first_snap),
            })
        return stats

    def undo_stack_summary(self) -> List[str]:
        return [f"#{e.seq} {e.action} {e.path}" for e in self.stack]
