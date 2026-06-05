"""Single-origin Splatial server: capture page + reconstruct API + built viewer + scene files.

One Flask app on one port replaces the old upload_server (:8090) + Vite (:5173) pair. Because
everything is same-origin there is no CORS, and because the container has one Python env there
is no conda shell-out. COOP/COEP are set so the viewer's gpu-accelerated splat sort can use
SharedArrayBuffer.
"""
import json
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parents[2]
SCENE_RE = re.compile(r"^[a-z0-9_-]{1,40}$")
ALLOWED_EXT = {"mp4", "mov", "m4v", "webm", "avi"}

CAPTURE_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Splatial — capture</title>
<style>body{{font-family:system-ui;margin:0;padding:24px;background:#111;color:#eee}}
h1{{font-size:20px}} input,button{{font-size:18px;padding:12px;margin:8px 0;width:100%;box-sizing:border-box}}
button{{background:#5e35b1;color:#fff;border:0;border-radius:8px}} a{{color:#9c7bff}}
.tip{{color:#aaa;font-size:14px;line-height:1.5}}</style></head><body>
<h1>📸 Splatial — capture a room</h1>
<p class=tip><b>Best quality:</b> record with your phone's <b>native Camera app</b>, then pick that file below. A <b>slow, steady sweep</b> (~15–25s), moving <i>around</i> the area for parallax, good light, lots of overlap.</p>
<form method=post action=/upload enctype=multipart/form-data>
  <input name=scene placeholder="scene name (e.g. room2)" value="room2" pattern="[a-z0-9_-]+" required>
  <input type=file name=video accept="video/*" required>
  <button type=submit>Upload &amp; reconstruct</button>
</form>
<p class=tip>Reconstructs in ~1–2 min, then links to the 3D viewer.</p>
<h2 style="font-size:17px;margin-top:28px">🗂️ Your scenes</h2>
<div id=gallery>{gallery}</div>
<script>
function delScene(n){{
  if(!confirm('Delete scene "'+n+'"? (moved to scenes/.trash — recoverable)')) return;
  fetch('/delete/'+encodeURIComponent(n),{{method:'POST'}})
    .then(r=>r.ok?location.reload():r.text().then(t=>alert('Delete failed: '+t)));
}}
</script></body></html>"""

RESULT_PAGE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Splatial — {scene}</title>
<style>body{{font-family:system-ui;margin:0;padding:24px;background:#111;color:#eee;text-align:center}}
a.btn{{display:inline-block;font-size:20px;padding:16px 24px;background:#5e35b1;color:#fff;border-radius:10px;text-decoration:none;margin-top:16px}}
#s{{font-size:18px;margin-top:24px}}</style></head><body>
<h1>Reconstructing "{scene}"…</h1>
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


def subprocess_recon_launcher(video: str, scene: str, scenes_root: Path, status: dict):
    """Default launcher: run the reconstruct CLI in THIS interpreter's env (no conda).

    Runs as a subprocess so the model's VRAM is freed on process exit. MAX_VIEWS is inherited
    from the parent env (set by __main__ from the detected GPU)."""
    def run():
        try:
            subprocess.run(
                [sys.executable, "-m", "modules.reconstruct.cli", video, "scenes", scene],
                cwd=str(ROOT), check=True, capture_output=True, text=True, timeout=1200,
            )
            status[scene] = "done"
        except subprocess.CalledProcessError as e:
            log = scenes_root / scene
            log.mkdir(parents=True, exist_ok=True)
            (log / "recon.log").write_text((e.stdout or "") + "\n--- STDERR ---\n" + (e.stderr or ""))
            detail = (e.stderr or e.stdout or "failed").strip()
            status[scene] = f"error: {detail[-600:]}"
        except Exception as e:  # noqa: BLE001
            status[scene] = f"error: {e}"

    threading.Thread(target=run, daemon=True).start()


def create_app(scenes_root=None, data_root=None, viewer_dist=None, assets_root=None,
               recon_launcher=subprocess_recon_launcher) -> Flask:
    scenes_root = Path(scenes_root or ROOT / "scenes")
    data_root = Path(data_root or ROOT / "data")
    viewer_dist = Path(viewer_dist or ROOT / "web" / "dist")
    assets_root = Path(assets_root or ROOT / "assets")
    status: dict[str, str] = {}

    app = Flask(__name__)
    app.config.update(SCENES=str(scenes_root), DATA=str(data_root), STATUS=status)

    @app.after_request
    def _isolation(resp):
        # SharedArrayBuffer (gpu-accelerated splat sort) needs cross-origin isolation.
        resp.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        resp.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
        return resp

    def _gallery() -> str:
        if not scenes_root.exists():
            return "<p class=tip>No scenes yet — capture one above.</p>"
        names = sorted(
            d.name for d in scenes_root.iterdir()
            if d.is_dir() and SCENE_RE.match(d.name)
            and ((d / "scene.ply").exists() or (d / "scene.json").exists())
        )
        if not names:
            return "<p class=tip>No scenes yet — capture one above.</p>"
        rows = []
        for s in names:
            st = status.get(s, "")
            badge = " ⏳" if st == "processing" else (" ❌" if st.startswith("error") else "")
            rows.append(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:12px;margin:8px 0;background:#1c1c22;border-radius:8px">'
                f'<span style="font-size:17px">{s}{badge}</span>'
                f'<span style="display:flex;gap:8px;align-items:center;width:auto">'
                f'<a class=btn href="/view?scene={s}" style="width:auto;padding:8px 16px;'
                f'background:#5e35b1;color:#fff;border-radius:8px;text-decoration:none">View 3D →</a>'
                f'<button onclick="delScene(\'{s}\')" title="Delete" '
                f'style="width:auto;margin:0;padding:8px 12px;background:#933;font-size:16px">🗑</button>'
                f'</span></div>'
            )
        return "".join(rows)

    @app.get("/")
    def index():
        return CAPTURE_PAGE.format(gallery=_gallery())

    @app.get("/healthz")
    def healthz():
        return jsonify(ok=True)

    @app.get("/view")
    @app.get("/view/")
    def view_index():
        return send_from_directory(viewer_dist, "index.html")

    @app.get("/view/<path:p>")
    def view_asset(p):
        full = (viewer_dist / p)
        if full.is_file():
            return send_from_directory(viewer_dist, p)
        return send_from_directory(viewer_dist, "index.html")  # SPA fallback

    @app.get("/scenes/<path:p>")
    def scene_file(p):
        return send_from_directory(scenes_root, p)

    @app.get("/assets/<path:p>")
    def asset_file(p):
        return send_from_directory(assets_root, p)

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
        data_root.mkdir(parents=True, exist_ok=True)
        video_path = data_root / f"{scene}.{ext}"
        f.save(str(video_path))
        status[scene] = "processing"
        recon_launcher(str(video_path), scene, scenes_root, status)
        return RESULT_PAGE.format(scene=scene, scene_json=json.dumps(scene),
                                  viewer_json=json.dumps(f"/view?scene={scene}"))

    @app.get("/status/<scene>")
    def get_status(scene):
        if not SCENE_RE.match(scene):
            return jsonify(state="error: bad scene"), 400
        return jsonify(state=status.get(scene, "unknown"))

    @app.post("/up/<scene>")
    def set_up(scene):
        if not SCENE_RE.match(scene):
            return "invalid scene name", 400
        d = (scenes_root / scene).resolve()
        sj = d / "scene.json"
        if d.parent != scenes_root.resolve() or not sj.exists():
            return "no such scene", 404
        data = request.get_json(silent=True) or {}
        up = data.get("up")
        if not (isinstance(up, list) and len(up) == 3 and all(isinstance(x, (int, float)) for x in up)):
            return "up must be [x,y,z]", 400
        meta = json.loads(sj.read_text())
        meta["up"] = [float(x) for x in up]
        sj.write_text(json.dumps(meta, indent=2))
        return jsonify(ok=True, up=meta["up"])

    @app.post("/delete/<scene>")
    def delete(scene):
        if not SCENE_RE.match(scene):
            return "invalid scene name", 400
        d = (scenes_root / scene).resolve()
        if d.parent != scenes_root.resolve() or not d.is_dir():
            return "no such scene", 404
        trash = scenes_root / ".trash"
        trash.mkdir(exist_ok=True)
        dest = trash / scene
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(d), str(dest))
        status.pop(scene, None)
        return jsonify(deleted=scene, recoverable=True)

    return app
