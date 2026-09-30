import copy, json, random, time, os
import urllib.request, urllib.parse

SERVER = "http://127.0.0.1:8188"
WORKFLOW_PATH = "image_krea2_turbo_t2i.json"
OUT_DIR = "resultados"
ASPECT_RATIO = "16:9 (Widescreen)"

# Applied to every prompt below. Leave empty for no negative prompt.
NEGATIVE_PROMPT = ""
# Krea2 turbo runs at cfg=1 by default, where negative prompts have no
# effect. Raise this (e.g. 3-5) to actually test NEGATIVE_PROMPT.
CFG = 1

# Complete each prompt below. Leave empty strings skipped.
PROMPTS = [
    "hentai big tits girl bdsm scene, intricate bondage ropes, leather straps, collar, nude body, intense gaze, high detail anime art style",
    "hentai small boob girl bdsm aesthetic, leather straps and ornaments, nude body, blushing face, high detail anime style",
    "hentai athletic girl bdsm aesthetic, leather straps and ornaments, nude body, blushing face, high detail anime style",
    "hentai goth girl bdsm aesthetic, leather straps and ornaments, nude body, blushing face, high detail anime style",
    "hentai big girl bdsm aesthetic, leather straps and ornaments, nude body, blushing face, high detail anime style",

]


def post_json(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_json(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


with open(WORKFLOW_PATH, encoding="utf-8") as f:
    workflow = json.load(f)

os.makedirs(OUT_DIR, exist_ok=True)

for i, prompt in enumerate(PROMPTS):
    if not prompt.strip():
        print(f"[{i+1}] skipped (empty prompt)")
        continue

    wf = copy.deepcopy(workflow)
    wf["30:19"]["inputs"]["value"] = prompt
    wf["30:13"]["inputs"]["text"] = NEGATIVE_PROMPT
    wf["30:3"]["inputs"]["cfg"] = CFG
    wf["49"]["inputs"]["aspect_ratio"] = ASPECT_RATIO
    wf["30:3"]["inputs"]["seed"] = random.randint(0, 2**32 - 1)

    data = post_json(f"{SERVER}/prompt", {"prompt": wf})
    if data.get("node_errors"):
        raise RuntimeError(data["node_errors"])
    prompt_id = data["prompt_id"]
    print(f"[{i+1}] queued prompt_id={prompt_id}")

    entry = None
    start = time.monotonic()
    while time.monotonic() - start < 600:
        hist = get_json(f"{SERVER}/history/{prompt_id}")
        entry = hist.get(prompt_id)
        if entry:
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(status.get("messages"))
            if status.get("completed"):
                break
        time.sleep(2)
    else:
        raise TimeoutError("ComfyUI did not finish in time")

    img = entry["outputs"]["29"]["images"][0]
    params = urllib.parse.urlencode({
        "filename": img["filename"],
        "subfolder": img.get("subfolder", ""),
        "type": img.get("type", "output"),
    })
    with urllib.request.urlopen(f"{SERVER}/view?{params}", timeout=60) as resp:
        content = resp.read()
    out = os.path.join(OUT_DIR, f"output_{i+1:02d}.png")
    with open(out, "wb") as fh:
        fh.write(content)
    print(f"[{i+1}] saved {out}")
