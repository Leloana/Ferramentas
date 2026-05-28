import os
from pathlib2 import Path


def run_command(args):
    """Execute a Windows PowerShell command and return stdout + stderr"""
    import subprocess
    command = args["command"]
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30
    )
    return {
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode
    }


def read_file(args):
    """Read the full contents of a file"""
    path = Path(args["path"])
    content = path.read_text(encoding="utf-8")
    return {"content": content}


def write_file(args):
    """Write or overwrite a file with given content"""
    path = Path(args["path"])
    path.write_text(args["content"], encoding="utf-8")
    return {"status": "ok", "path": args["path"]}


def patch_file(args):
    """Replace the first occurrence of old_str with new_str in a file"""
    path = Path(args["path"])
    content = path.read_text(encoding="utf-8")
    old_str = args["old_str"]
    new_str = args["new_str"]
    if old_str not in content:
        return {"error": f"old_str not found in {args['path']}"}
    patched = content.replace(old_str, new_str, 1)
    path.write_text(patched, encoding="utf-8")
    return {"status": "patched", "path": args["path"]}


def list_dir(args):
    """List files and folders in a directory"""
    path = Path(args["path"])
    entries = os.listdir(args["path"])
    return {"entries": entries}


def search_file(args):
    """Search for a string inside a file, return matching lines with line numbers"""
    path = Path(args["path"]).read_text(encoding="utf-8")
    lines = path.splitlines()
    matches = []
    for i, line in enumerate(lines, start=1):
        if args["query"] in line:
            matches.append({"line": i, "content": line})
    return {"matches": matches}


def http_get(args):
    """Perform an HTTP GET request and return the response body (truncated to 3000 chars)"""
    import requests
    response = requests.get(args["url"], timeout=10)
    return {"body": response.text[:3000]}


def plan(args):
    """Generate a plan of action based on a prompt and write it to a file.
    
    Args:
        args: Dictionary with "prompt" key containing the prompt for plan generation.
        
    Returns:
        Dictionary with status, plan_path, and plan_content
    """
    prompt = args.get("prompt", "")
    working_dir = Path.cwd().resolve()
    plans_dir = working_dir / "plans"
    
    # Create plans directory if it doesn't exist
    plans_dir.mkdir(exist_ok=True)
    
    import time
    import ollama
    
    start_time = time.time()
    
    # Generate plan using Ollama
    try:
        stream = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        
        plan_content = ""
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "") if isinstance(chunk, dict) else getattr(chunk.message, "content", "")
            if token:
                plan_content += token
    except Exception as e:
        plan_content = f"Error generating plan: {str(e)}"
    
    elapsed = time.time() - start_time
    
    # Write plan to file with timestamp
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    plan_path = plans_dir / f"plan_{timestamp}.md"
    
    try:
        # Write plan with preamble
        full_content = f"# Plan Generated: {timestamp}\n\n{plan_content}\n\n---\n\n*Generated via /plan skill*\n"
        plan_path.write_text(full_content, encoding="utf-8")
        
        return {"status": "ok", "path": str(plan_path), "content": full_content}
    except Exception as e:
        return {"error": f"Failed to write plan file: {str(e)}"}
