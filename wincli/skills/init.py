"""Wrapper exposing the existing init_skill as a discoverable skill."""

NAME = "init"
DESCRIPTION = "Scan the project and regenerate WINCLI.md"


def run(args, ctx):
    from init_skill import generate_wincli
    ok = generate_wincli(ctx["working_dir"], ctx["model"])
    return {"status": "ok" if ok else "failed"}
