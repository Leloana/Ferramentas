"""Central UI layer for WINCLI.

Everything visual goes through here so the look stays consistent:

  - Strict black & white. The terminal's *default* colors are switched to
    white-on-black via OSC 10/11 escapes, so the whole window (including
    empty areas and scrollback) is painted black. Rich runs with
    ``no_color=True`` so every legacy ``[red]``/``[cyan]`` markup collapses
    to monochrome; only bold / dim / reverse survive to convey hierarchy.

  - No typed choices. ``select()`` is an arrow-key menu (Ôåæ/Ôåô + Enter) used
    for every decision in the app (model pick, permissions, resume, plan
    approval, ...).

  - A big "WINCLI" banner shown on launch.

  - Tiny JSON config (``~/.wincli_config.json``) that remembers the last
    chosen model so the chat opens straight into it.
"""

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style as PTStyle


# --- shared monochrome console -------------------------------------------
# no_color=True strips every color the rest of the codebase emits, leaving a
# clean black & white render. We keep markup like [bold]/[dim] working.
console = Console(no_color=True, highlight=False)


# --- terminal background --------------------------------------------------
def paint_background():
    """Switch the terminal's default colors to white-on-black and clear.

    Uses OSC 11 (background) / OSC 10 (foreground) so the *entire* terminal
    surface is black, not just the cells we print into. Then clears screen +
    scrollback. Supported by Windows Terminal and all modern emulators.
    """
    sys.stdout.write("\x1b]11;#000000\x07")   # default background -> black
    sys.stdout.write("\x1b]10;#ffffff\x07")   # default foreground -> white
    sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")  # clear screen + scrollback, home
    sys.stdout.flush()


def reset_background():
    """Restore the terminal's default colors on exit (be a good citizen)."""
    try:
        sys.stdout.write("\x1b]111\x07")  # reset default background
        sys.stdout.write("\x1b]110\x07")  # reset default foreground
        sys.stdout.flush()
    except Exception:
        pass


# --- header ---------------------------------------------------------------
_BANNER = r"""
ÔûêÔûêÔòù    ÔûêÔûêÔòùÔûêÔûêÔòùÔûêÔûêÔûêÔòù   ÔûêÔûêÔòù ÔûêÔûêÔûêÔûêÔûêÔûêÔòùÔûêÔûêÔòù     ÔûêÔûêÔòù
ÔûêÔûêÔòæ    ÔûêÔûêÔòæÔûêÔûêÔòæÔûêÔûêÔûêÔûêÔòù  ÔûêÔûêÔòæÔûêÔûêÔòöÔòÉÔòÉÔòÉÔòÉÔòØÔûêÔûêÔòæ     ÔûêÔûêÔòæ
ÔûêÔûêÔòæ ÔûêÔòù ÔûêÔûêÔòæÔûêÔûêÔòæÔûêÔûêÔòöÔûêÔûêÔòù ÔûêÔûêÔòæÔûêÔûêÔòæ     ÔûêÔûêÔòæ     ÔûêÔûêÔòæ
ÔûêÔûêÔòæÔûêÔûêÔûêÔòùÔûêÔûêÔòæÔûêÔûêÔòæÔûêÔûêÔòæÔòÜÔûêÔûêÔòùÔûêÔûêÔòæÔûêÔûêÔòæ     ÔûêÔûêÔòæ     ÔûêÔûêÔòæ
ÔòÜÔûêÔûêÔûêÔòöÔûêÔûêÔûêÔòöÔòØÔûêÔûêÔòæÔûêÔûêÔòæ ÔòÜÔûêÔûêÔûêÔûêÔòæÔòÜÔûêÔûêÔûêÔûêÔûêÔûêÔòùÔûêÔûêÔûêÔûêÔûêÔûêÔûêÔòùÔûêÔûêÔòæ
 ÔòÜÔòÉÔòÉÔòØÔòÜÔòÉÔòÉÔòØ ÔòÜÔòÉÔòØÔòÜÔòÉÔòØ  ÔòÜÔòÉÔòÉÔòÉÔòØ ÔòÜÔòÉÔòÉÔòÉÔòÉÔòÉÔòØÔòÜÔòÉÔòÉÔòÉÔòÉÔòÉÔòÉÔòØÔòÜÔòÉÔòØ
"""

_SUBTITLE = "the agent cli ÔÇö windows native"


def header():
    """Print the big WINCLI banner + subtitle."""
    width = max((len(l) for l in _BANNER.splitlines()), default=0)
    for line in _BANNER.strip("\n").splitlines():
        console.print(line, style="bold")
    console.print(_SUBTITLE.center(width), style="dim")
    console.print("ÔöÇ" * width, style="dim")


def rule(text=""):
    console.rule(text, style="dim", characters="ÔöÇ")


def panel(body, title="", subtitle=""):
    """A plain white-bordered panel (monochrome)."""
    console.print(Panel(body, title=title, subtitle=subtitle, border_style="white"))


def info(msg):
    console.print(msg)


def dim(msg):
    console.print(msg, style="dim")


# --- arrow-key selection menu --------------------------------------------
def select(options, *, title=None, default=0,
           footer="Ôåæ/Ôåô move ┬À enter select ┬À esc cancel"):
    """Arrow-key menu. The ONLY way the app asks the user to choose.

    options : list of either ``label`` strings or ``(label, value)`` tuples.
    Returns the chosen value (or the label if no value given), or ``None`` if
    the user cancels (Esc / Ctrl-C).
    """
    labels, values = [], []
    for o in options:
        if isinstance(o, tuple):
            labels.append(str(o[0]))
            values.append(o[1])
        else:
            labels.append(str(o))
            values.append(o)

    if not labels:
        return None

    state = {"i": max(0, min(default, len(labels) - 1))}

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(event):
        state["i"] = (state["i"] - 1) % len(labels)

    @kb.add("down")
    @kb.add("j")
    def _down(event):
        state["i"] = (state["i"] + 1) % len(labels)

    @kb.add("enter")
    def _accept(event):
        event.app.exit(result=state["i"])

    @kb.add("escape")
    @kb.add("c-c")
    @kb.add("q")
    def _cancel(event):
        event.app.exit(result=None)

    def render():
        frags = []
        if title:
            frags.append(("bold", title + "\n\n"))
        for i, lbl in enumerate(labels):
            if i == state["i"]:
                frags.append(("reverse", f" ÔØ» {lbl} "))
                frags.append(("", "\n"))
            else:
                frags.append(("", f"   {lbl}\n"))
        frags.append(("", "\n"))
        frags.append(("class:footer", footer))
        return frags

    height = len(labels) + (2 if title else 0) + 2
    window = Window(
        content=FormattedTextControl(render, focusable=True),
        height=height,
        always_hide_cursor=True,
    )
    style = PTStyle.from_dict({
        "footer": "#888888",
    })
    app = Application(
        layout=Layout(HSplit([window])),
        key_bindings=kb,
        style=style,
        full_screen=False,
        mouse_support=False,
    )
    idx = app.run()
    if idx is None:
        return None
    return values[idx]


def confirm(question, *, default_yes=False):
    """Yes/No as an arrow menu. Returns True/False (None on cancel -> False)."""
    res = select(
        [("yes", True), ("no", False)],
        title=question,
        default=0 if default_yes else 1,
        footer="Ôåæ/Ôåô move ┬À enter confirm",
    )
    return bool(res)


# --- config (last model memory) ------------------------------------------
CONFIG_PATH = Path.home() / ".wincli_config.json"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    except Exception:
        pass


def get_last_model():
    return load_config().get("model")


def set_last_model(model):
    cfg = load_config()
    cfg["model"] = model
    save_config(cfg)
