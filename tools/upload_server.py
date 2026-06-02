"""Splatial phone capture server.

Open this on your phone (same Wi-Fi), record/upload a room sweep, and it runs the
AnySplat reconstruction in the background, then links you to the web viewer.

Run (from repo root, in the .venv):
    python tools/upload_server.py            # serves on 0.0.0.0:8000

It shells out to the `anysplat` conda env for the actual reconstruction, and the
viewer is the separately-running Vite dev server on :5173.
"""
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

from flask import Flask, request, jsonify

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SCENES = ROOT / "scenes"
CONDA = "/home/liylo/anaconda3/condabin/conda"
VIEWER_PORT = 5173
SCENE_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,255}$")
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
<p class=tip><b>Best quality:</b> record with your phone's <b>native Camera app</b> (sharper/stabilized), then pick that file below. A <b>slow, steady sweep</b> (~15–25s), moving <i>around</i> the area for parallax, good light, lots of overlap. (Frames are processed at 448px, so framing &amp; steadiness matter more than resolution.)</p>
<form method=post action=/upload enctype=multipart/form-data>
  <input name=scene placeholder="scene name (e.g. room2)" value="room2" pattern="[a-z0-9_-]+" required>
  <input type=file name=video accept="video/*" required>
  <button type=submit>Upload &amp; reconstruct</button>
</form>
<p class=tip>Pick an existing recording (recommended) or your camera. Reconstructs in ~1–2 min, then links to the 3D viewer.</p>
<h2 style="font-size:17px;margin-top:28px">🗂️ Your scenes</h2>
<div id=gallery>{gallery}</div>
<script>
function delScene(n){{
  if(!confirm('Delete scene "'+n+'"? This permanently removes its folder and cannot be undone.')) return;
  fetch('/delete/'+encodeURIComponent(n),{{method:'POST'}})
    .then(r=>r.ok?location.reload():r.text().then(t=>alert('Delete failed: '+t)));
}}
</script>
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
const scene={scene_json};
const viewer={viewer_json};
async function poll(){{
  const r=await fetch("/status/"+encodeURIComponent(scene)); const j=await r.json();
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


def _build_gallery(host: str) -> str:
    """Live listing of reconstructed scenes with one-click viewer links."""
    if not SCENES.exists():
        return "<p class=tip>No scenes yet — capture one above.</p>"
    scenes = sorted(
        d.name for d in SCENES.iterdir()
        if d.is_dir() and SCENE_RE.match(d.name)
        and ((d / "scene.ply").exists() or (d / "scene.json").exists())
    )
    if not scenes:
        return "<p class=tip>No scenes yet — capture one above.</p>"
    rows = []
    for s in scenes:
        state = STATUS.get(s, "")
        badge = " ⏳" if state == "processing" else (" ❌" if state.startswith("error") else "")
        url = f"http://{host}:{VIEWER_PORT}/?scene={s}"
        rows.append(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:12px;margin:8px 0;background:#1c1c22;border-radius:8px">'
            f'<span style="font-size:17px">{s}{badge}</span>'
            f'<span style="display:flex;gap:8px;align-items:center;width:auto">'
            f'<a class=btn href="{url}" '
            f'style="display:inline-block;width:auto;padding:8px 16px;'
            f'background:#5e35b1;color:#fff;border-radius:8px;text-decoration:none">View 3D →</a>'
            f'<button onclick="delScene(\'{s}\')" title="Delete scene" '
            f'style="width:auto;margin:0;padding:8px 12px;background:#933;font-size:16px">🗑</button>'
            f'</span></div>'
        )
    return "".join(rows)


@app.get("/")
def index():
    host = request.host.split(":")[0]
    if not HOST_RE.match(host):
        return "invalid host header", 400
    return PAGE.format(gallery=_build_gallery(host))


@app.route("/up/<scene>", methods=["POST", "OPTIONS"])
def set_up(scene):
    # Persist a hand-leveled up vector from the viewer (cross-origin :5173 -> :8090, so CORS).
    # Scope CORS to the viewer origin on THIS host (not '*'), so a random site can't rewrite
    # scene.json via the user's browser. The viewer always calls us at location.hostname:8090,
    # so its Origin is http://<this-host>:5173 — echo exactly that (host validated).
    host = request.host.split(":")[0]
    if not HOST_RE.match(host):
        return "invalid host header", 400
    allowed_origin = f"http://{host}:{VIEWER_PORT}"
    cors = {"Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Vary": "Origin"}
    if request.method == "OPTIONS":
        return ("", 204, cors)
    # Defense in depth: CORS headers are browser-enforced, so ALSO reject server-side any
    # request whose Origin isn't the viewer (a forged cross-site POST carries a foreign Origin;
    # legitimate same-origin/non-browser callers send none).
    origin = request.headers.get("Origin")
    if origin is not None and origin != allowed_origin:
        return ("forbidden origin", 403, cors)
    if not SCENE_RE.match(scene):
        return ("invalid scene name", 400, cors)
    d = (SCENES / scene).resolve()
    sj = d / "scene.json"
    if d.parent != SCENES.resolve() or not sj.exists():
        return ("no such scene", 404, cors)
    data = request.get_json(silent=True) or {}
    up = data.get("up")
    if not (isinstance(up, list) and len(up) == 3 and all(isinstance(x, (int, float)) for x in up)):
        return ("up must be [x,y,z]", 400, cors)
    meta = json.loads(sj.read_text())
    meta["up"] = [float(x) for x in up]
    sj.write_text(json.dumps(meta, indent=2))
    return (json.dumps({"ok": True, "up": meta["up"]}), 200, {**cors, "Content-Type": "application/json"})


@app.post("/delete/<scene>")
def delete(scene):
    # SCENE_RE blocks path separators / '..'; double-check the resolved path stays in SCENES.
    if not SCENE_RE.match(scene):
        return "invalid scene name", 400
    d = (SCENES / scene).resolve()
    if d.parent != SCENES.resolve() or not d.is_dir():
        return "no such scene", 404
    shutil.rmtree(d)
    STATUS.pop(scene, None)
    return jsonify(deleted=scene)


@app.post("/upload")
def upload():
    scene = (request.form.get("scene") or "").strip().lower()
    if not SCENE_RE.match(scene):
        return "invalid scene name (use a-z 0-9 _ -)", 400
    # Validate the Host header up front (before any side effects) — it is reflected into
    # the response, so reject anything outside a strict hostname/IP charset.
    host = request.host.split(":")[0]
    if not HOST_RE.match(host):
        return "invalid host header", 400
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
    viewer_url = f"http://{host}:{VIEWER_PORT}/?scene={scene}"
    # scene is [a-z0-9_-] (safe in HTML); JS values are JSON-encoded for JS-context safety.
    return RESULT.format(scene=scene, scene_json=json.dumps(scene),
                         viewer_json=json.dumps(viewer_url))


@app.get("/status/<scene>")
def status(scene):
    if not SCENE_RE.match(scene):
        return jsonify(state="error: bad scene"), 400
    return jsonify(state=STATUS.get(scene, "unknown"))


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8090")), threaded=True)
