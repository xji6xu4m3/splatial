"""Splatial phone capture server.

Open this on your phone (same Wi-Fi), record/upload a room sweep, and it runs the
AnySplat reconstruction in the background, then links you to the web viewer.

Run (from repo root, in the .venv):
    python tools/upload_server.py            # serves on 0.0.0.0:8000

It shells out to the `anysplat` conda env for the actual reconstruction, and the
viewer is the separately-running Vite dev server on :5173.
"""
import re
import subprocess
import threading
from pathlib import Path

from flask import Flask, request, jsonify, redirect

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCENES = ROOT / "scenes"
CONDA = "/home/liylo/anaconda3/condabin/conda"
VIEWER_PORT = 5173
SCENE_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
ALLOWED_EXT = {"mp4", "mov", "m4v", "webm", "avi"}

app = Flask(__name__)
STATUS: dict[str, str] = {}  # scene -> processing | done | error: <msg>

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Splatial — capture</title>
<style>body{{font-family:system-ui;margin:0;padding:24px;background:#111;color:#eee}}
h1{{font-size:20px}} input,button{{font-size:18px;padding:12px;margin:8px 0;width:100%;box-sizing:border-box}}
button{{background:#5e35b1;color:#fff;border:0;border-radius:8px}} a{{color:#9c7bff}}
.tip{{color:#aaa;font-size:14px;line-height:1.5}}</style></head><body>
<h1>📸 Splatial — capture a room</h1>
<p class=tip>Record a <b>slow, steady sweep</b> (~15–25s) of a small area — move <i>around</i> objects for parallax, keep good light, lots of overlap.</p>
<form method=post action=/upload enctype=multipart/form-data>
  <input name=scene placeholder="scene name (e.g. room2)" value="room2" pattern="[a-z0-9_-]+" required>
  <input type=file name=video accept="video/*" capture="environment" required>
  <button type=submit>Upload &amp; reconstruct</button>
</form>
<p class=tip>After upload it reconstructs in ~1–2 min, then shows a link to the 3D viewer.</p>
</body></html>"""

RESULT = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Splatial — {scene}</title>
<style>body{{font-family:system-ui;margin:0;padding:24px;background:#111;color:#eee;text-align:center}}
a.btn{{display:inline-block;font-size:20px;padding:16px 24px;background:#5e35b1;color:#fff;border-radius:10px;text-decoration:none;margin-top:16px}}
#s{{font-size:18px;margin-top:24px}}</style></head><body>
<h1>Reconstructing “{scene}”…</h1>
<div id=s>⏳ working — this takes ~1–2 min</div>
<div id=link></div>
<script>
const scene="{scene}", viewer="http://{host}:{port}/?scene="+scene;
async function poll(){{
  const r=await fetch("/status/"+scene); const j=await r.json();
  if(j.state==="done"){{document.getElementById('s').textContent="✅ done!";
    const a=document.createElement('a'); a.className='btn'; a.href=viewer; a.textContent='Open 3D viewer →';
    document.getElementById('link').replaceChildren(a);}}
  else if(j.state && j.state.startsWith("error")){{document.getElementById('s').textContent="❌ "+j.state;}}
  else setTimeout(poll,3000);
}}
poll();
</script></body></html>"""


def _reconstruct(video: str, scene: str):
    try:
        subprocess.run(
            [CONDA, "run", "-n", "anysplat", "--no-capture-output", "env",
             f"ANYSPLAT_ROOT={ROOT}/external_AnySplat", "RECON_ENGINE=anysplat",
             "python", "-m", "modules.reconstruct.cli", video, "scenes", scene],
            cwd=str(ROOT), check=True, capture_output=True, text=True, timeout=900,
        )
        STATUS[scene] = "done"
    except subprocess.CalledProcessError as e:
        STATUS[scene] = f"error: {(e.stderr or e.stdout or 'failed')[-200:]}"
    except Exception as e:  # noqa: BLE001
        STATUS[scene] = f"error: {e}"


@app.get("/")
def index():
    return PAGE


@app.post("/upload")
def upload():
    scene = (request.form.get("scene") or "").strip().lower()
    if not SCENE_RE.match(scene):
        return "invalid scene name (use a-z 0-9 _ -)", 400
    f = request.files.get("video")
    if not f or not f.filename:
        return "no video uploaded", 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else "mp4"
    if ext not in ALLOWED_EXT:
        ext = "mp4"
    DATA.mkdir(exist_ok=True)
    video_path = DATA / f"{scene}.{ext}"
    f.save(str(video_path))
    STATUS[scene] = "processing"
    threading.Thread(target=_reconstruct, args=(str(video_path), scene), daemon=True).start()
    host = request.host.split(":")[0]
    return RESULT.format(scene=scene, host=host, port=VIEWER_PORT)


@app.get("/status/<scene>")
def status(scene):
    if not SCENE_RE.match(scene):
        return jsonify(state="error: bad scene"), 400
    return jsonify(state=STATUS.get(scene, "unknown"))


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8090")), threaded=True)
