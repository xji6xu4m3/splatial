# One-Command Phone Onboarding (Docker) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the whole capture → reconstruct → view pipeline into one prebuilt Docker image that a non-developer runs with a single `docker run`, reaching it from a phone via a printed URL + QR.

**Architecture:** A single Flask server (`modules/serve`) serves the capture page, the reconstruct API, the built Three.js viewer, and the `scenes/` files on **one port** — no conda, no second server, no CORS. The image bakes CUDA torch + AnySplat + weights, auto-scales the view cap to the host GPU's VRAM, and prints a LAN URL + QR on startup. Published prebuilt to GHCR.

**Tech Stack:** Python/Flask, PyTorch 2.2 + CUDA 12.1, AnySplat, Vite/Three.js, Docker (multi-stage), GitHub Actions → GHCR, `qrcode`.

**Spec:** `docs/superpowers/specs/2026-06-05-phone-docker-onboarding-design.md`

---

## File Structure

**New (Python serve package — replaces `tools/upload_server.py`):**
- `modules/serve/__init__.py` — package marker
- `modules/serve/gpu.py` — pure: VRAM bytes → default `MAX_VIEWS`
- `modules/serve/net.py` — pure: LAN IP, viewer URL, ASCII QR, startup banner
- `modules/serve/app.py` — Flask `create_app(recon_launcher)` with all routes
- `modules/serve/__main__.py` — entrypoint: detect VRAM, print banner, run app
- `modules/serve/tests/test_gpu.py`, `test_net.py`, `test_app.py`

**New (packaging):**
- `Dockerfile`, `.dockerignore`
- `.github/workflows/docker-publish.yml`

**Modified:**
- `web/vite.config.js` — `base: '/view/'`
- `web/src/main.js:15` — home link → `/`
- `web/src/level.js:58` — up-save → relative `/up/<scene>`
- `README.md` — add "Run on your phone (Docker)" section
- `pyproject.toml` — add `qrcode` to `serve` extra
- Delete `tools/upload_server.py` (logic ported into `modules/serve/app.py`)

**Unchanged:** `modules/reconstruct/*`, `modules/capture/*`, `modules/scene_store/*`, viewer rendering logic.

---

## Task 1: VRAM → default view-cap helper

**Files:**
- Create: `modules/serve/__init__.py` (empty)
- Create: `modules/serve/gpu.py`
- Create: `modules/serve/tests/__init__.py` (empty)
- Test: `modules/serve/tests/test_gpu.py`

- [ ] **Step 1: Create empty package markers**

```bash
mkdir -p modules/serve/tests
: > modules/serve/__init__.py
: > modules/serve/tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

`modules/serve/tests/test_gpu.py`:
```python
import pytest
from modules.serve.gpu import default_max_views

GB = 1024 ** 3

@pytest.mark.parametrize("vram_gb, expected", [
    (8, 16), (11.5, 16), (12, 16),     # <=12GB cards (4070 Ti) -> 16
    (16, 32), (24, 32), (32, 32),      # 16-24GB (3090/4090) -> 32
    (40, 48), (48, 48), (80, 48),      # >=40GB (A100/L40S) -> 48
])
def test_default_max_views(vram_gb, expected):
    assert default_max_views(int(vram_gb * GB)) == expected

def test_zero_or_unknown_falls_back_to_16():
    assert default_max_views(0) == 16
    assert default_max_views(None) == 16
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest modules/serve/tests/test_gpu.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.serve.gpu'`

- [ ] **Step 4: Write minimal implementation**

`modules/serve/gpu.py`:
```python
"""Pick a default reconstruction view cap that matches the host GPU's VRAM.

Bigger card -> more input views fit -> denser scan. Thresholds mirror the design spec:
<16GB -> 16, <40GB -> 32, else 48. Overridable via the MAX_VIEWS env var downstream.
"""

GB = 1024 ** 3


def default_max_views(total_vram_bytes: int | None) -> int:
    if not total_vram_bytes or total_vram_bytes <= 0:
        return 16
    gb = total_vram_bytes / GB
    if gb < 16:
        return 16
    if gb < 40:
        return 32
    return 48
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest modules/serve/tests/test_gpu.py -v`
Expected: PASS (11 cases)

- [ ] **Step 6: Commit**

```bash
git add modules/serve/__init__.py modules/serve/gpu.py modules/serve/tests/__init__.py modules/serve/tests/test_gpu.py
git commit -m "feat(serve): VRAM->default-view-cap helper"
```

---

## Task 2: LAN IP, viewer URL, QR banner helpers

**Files:**
- Create: `modules/serve/net.py`
- Test: `modules/serve/tests/test_net.py`

- [ ] **Step 1: Write the failing test**

`modules/serve/tests/test_net.py`:
```python
import re
from modules.serve import net

def test_lan_ip_returns_dotted_quad():
    ip = net.lan_ip()
    assert re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip)

def test_lan_ip_falls_back_on_error(monkeypatch):
    class BoomSocket:
        def __init__(self, *a, **k): pass
        def connect(self, *a, **k): raise OSError("no network")
        def getsockname(self): raise AssertionError("unreachable")
        def close(self): pass
    monkeypatch.setattr(net.socket, "socket", BoomSocket)
    assert net.lan_ip() == "127.0.0.1"

def test_viewer_url():
    assert net.viewer_url("192.168.1.5", 8080) == "http://192.168.1.5:8080"

def test_qr_ascii_is_nonempty_multiline():
    art = net.qr_ascii("http://192.168.1.5:8080")
    assert isinstance(art, str) and "\n" in art and len(art) > 50

def test_banner_contains_url(monkeypatch):
    monkeypatch.setattr(net, "lan_ip", lambda: "10.0.0.9")
    text = net.startup_banner(8080)
    assert "http://10.0.0.9:8080" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest modules/serve/tests/test_net.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.serve.net'`

- [ ] **Step 3: Write minimal implementation**

`modules/serve/net.py`:
```python
"""Host-network helpers: find the LAN IP and render the startup banner + QR.

The phone reaches the container at the host's LAN IP (we run with --network host), so we
detect it via a UDP socket to a public address (no packets actually sent) and fall back to
loopback if there's no network.
"""
import socket

import qrcode


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # no traffic; just selects the outbound interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        try:
            s.close()
        except OSError:
            pass


def viewer_url(ip: str, port: int) -> str:
    return f"http://{ip}:{port}"


def qr_ascii(text: str) -> str:
    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.make(fit=True)
    rows = qr.get_matrix()
    return "\n".join("".join("██" if cell else "  " for cell in row) for row in rows)


def startup_banner(port: int) -> str:
    url = viewer_url(lan_ip(), port)
    return (
        "\n" + "=" * 48 + "\n"
        "  Splatial is live. On your phone, open:\n"
        f"      {url}\n"
        "  (the phone must share this Wi-Fi)\n\n"
        f"{qr_ascii(url)}\n"
        + "=" * 48 + "\n"
    )
```

- [ ] **Step 4: Add `qrcode` to the serve extra**

Modify `pyproject.toml`, change the `serve` line under `[project.optional-dependencies]`:
```toml
serve = ["flask>=3.0", "qrcode>=7.4"]
```

- [ ] **Step 5: Install and run tests**

Run: `pip install -e ".[dev,serve]" && pytest modules/serve/tests/test_net.py -v`
Expected: PASS (5 cases)

- [ ] **Step 6: Commit**

```bash
git add modules/serve/net.py modules/serve/tests/test_net.py pyproject.toml
git commit -m "feat(serve): LAN IP + viewer URL + ASCII-QR startup banner"
```

---

## Task 3: Unified Flask app (ports upload_server routes + viewer/static/healthz)

This ports every route from `tools/upload_server.py` into a testable `create_app()` factory, swaps the conda subprocess for a same-env one, makes all URLs same-origin, and adds `/view`, `/scenes`, `/assets`, `/healthz`, and COOP/COEP headers.

**Files:**
- Create: `modules/serve/app.py`
- Test: `modules/serve/tests/test_app.py`

- [ ] **Step 1: Write the failing test**

`modules/serve/tests/test_app.py`:
```python
import io
import json
from pathlib import Path

import pytest

from modules.serve.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    # isolate scenes/ data/ to a temp dir; record recon launches instead of running torch
    launched = []

    def fake_launcher(video, scene, scenes_root, status):
        launched.append((video, scene))
        d = Path(scenes_root) / scene
        d.mkdir(parents=True, exist_ok=True)
        (d / "scene.json").write_text(json.dumps({"id": scene, "ply": "scene.ply", "up": [0, 1, 0]}))
        status[scene] = "done"

    app = create_app(
        scenes_root=tmp_path / "scenes",
        data_root=tmp_path / "data",
        viewer_dist=tmp_path / "dist",
        assets_root=tmp_path / "assets",
        recon_launcher=fake_launcher,
    )
    # a minimal built viewer + a scene to serve
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<!doctype html><title>viewer</title>")
    app.config["LAUNCHED"] = launched
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_is_capture_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"capture" in r.data.lower()


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_view_serves_viewer_build(client):
    r = client.get("/view")
    assert r.status_code == 200 and b"viewer" in r.data.lower()


def test_coop_coep_headers_present(client):
    r = client.get("/view")
    assert r.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert r.headers["Cross-Origin-Embedder-Policy"] == "credentialless"


def test_upload_enqueues_and_serves_scene(client, app):
    data = {"scene": "room9", "video": (io.BytesIO(b"fakevideo"), "room9.mp4")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert app.config["LAUNCHED"] == [(str(Path(app.config["DATA"]) / "room9.mp4"), "room9")]
    # scene.json now served same-origin
    sj = client.get("/scenes/room9/scene.json")
    assert sj.status_code == 200 and sj.get_json()["id"] == "room9"


def test_upload_rejects_bad_scene_name(client):
    data = {"scene": "Bad Name!", "video": (io.BytesIO(b"x"), "x.mp4")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_result_page_links_to_same_origin_view(client):
    data = {"scene": "room8", "video": (io.BytesIO(b"x"), "room8.mp4")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert b"/view?scene=room8" in r.data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest modules/serve/tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'modules.serve.app'`

- [ ] **Step 3: Write the implementation**

`modules/serve/app.py`:
```python
"""Single-origin Splatial server: capture page + reconstruct API + built viewer + scene files.

One Flask app on one port replaces the old upload_server (:8090) + Vite (:5173) pair. Because
everything is same-origin there is no CORS, and because the container has one Python env there
is no conda shell-out. COOP/COEP are set so the viewer's gpu-accelerated splat sort can use
SharedArrayBuffer.
"""
import json
import os
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


def subprocess_recon_launcher(video: str, scene: str, scenes_root: Path, status: dict):
    """Default launcher: run the reconstruct CLI in THIS interpreter's env (no conda).

    Runs as a subprocess so the model's VRAM is freed on process exit. MAX_VIEWS is inherited
    from the parent env (set by __main__ from the detected GPU)."""
    def run():
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "modules.reconstruct.cli", video, "scenes", scene],
                cwd=str(ROOT), check=True, capture_output=True, text=True, timeout=1200,
            )
            _ = proc
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest modules/serve/tests/test_app.py -v`
Expected: PASS (8 cases)

- [ ] **Step 5: Commit**

```bash
git add modules/serve/app.py modules/serve/tests/test_app.py
git commit -m "feat(serve): single-origin Flask app (capture+viewer+scenes+healthz, no CORS/conda)"
```

---

## Task 4: Entrypoint — detect GPU, print banner, run

**Files:**
- Create: `modules/serve/__main__.py`

- [ ] **Step 1: Write the entrypoint**

`modules/serve/__main__.py`:
```python
"""`python -m modules.serve` — detect the GPU's VRAM to set the default view cap, print the
phone URL + QR, then serve. Run with --network host so the LAN IP is reachable from a phone.
"""
import os

from modules.serve.app import create_app
from modules.serve.gpu import default_max_views
from modules.serve.net import startup_banner


def _detect_total_vram() -> int | None:
    try:
        import torch
        if not torch.cuda.is_available():
            print("WARNING: no CUDA GPU visible — run with `--gpus all` and "
                  "nvidia-container-toolkit. Reconstruction will fail until then.")
            return None
        return torch.cuda.get_device_properties(0).total_memory
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: could not query GPU ({e}); defaulting view cap to 16.")
        return None


def main():
    if "MAX_VIEWS" not in os.environ:
        cap = default_max_views(_detect_total_vram())
        os.environ["MAX_VIEWS"] = str(cap)
        os.environ.setdefault("MIN_VIEWS", str(cap))
        print(f"GPU view cap (MAX_VIEWS) auto-set to {cap}")

    port = int(os.environ.get("PORT", "8080"))
    print(startup_banner(port))
    app = create_app()
    app.run(host="0.0.0.0", port=port, threaded=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it boots and serves locally (no GPU needed)**

Run:
```bash
pip install -e ".[dev,serve]"
mkdir -p web/dist && echo '<!doctype html><title>viewer</title>' > web/dist/index.html
PORT=8080 timeout 4 python -m modules.serve &
sleep 2 && curl -s localhost:8080/healthz && curl -s -o /dev/null -w " /=%{http_code}\n" localhost:8080/
```
Expected: prints `{"ok":true}` and ` /=200`, and the banner with a QR block appeared in the background-process output.

- [ ] **Step 3: Commit**

```bash
git add modules/serve/__main__.py
git commit -m "feat(serve): entrypoint with GPU VRAM autoscale + URL/QR banner"
```

---

## Task 5: Viewer — production build base + same-origin links

**Files:**
- Modify: `web/vite.config.js`
- Modify: `web/src/main.js:15`
- Modify: `web/src/level.js:58`

- [ ] **Step 1: Set the build base so viewer assets live under `/view/`**

In `web/vite.config.js`, change the `export default defineConfig({...})` call to add `base` (keeps the existing `crossOriginIsolation` plugin and `server` block):
```javascript
export default defineConfig({
  base: '/view/',
  plugins: [crossOriginIsolation],
  server: { host: true, port: 5173, fs: { allow: ['..'] } },
})
```

- [ ] **Step 2: Point the viewer's "home" link at the same-origin capture page**

In `web/src/main.js`, replace line 15:
```javascript
home.href = `http://${location.hostname}:8090/`
```
with:
```javascript
home.href = '/'
```

- [ ] **Step 3: Make the up-vector save same-origin**

In `web/src/level.js`, replace the fetch on line 58:
```javascript
    fetch(`http://${location.hostname}:8090/up/${encodeURIComponent(sceneId)}`, {
```
with:
```javascript
    fetch(`/up/${encodeURIComponent(sceneId)}`, {
```

- [ ] **Step 4: Build and verify the output exists with the right base**

Run:
```bash
cd web && npm install && npm run build
test -f dist/index.html && grep -q '/view/assets/' dist/index.html && echo "BUILD OK: assets under /view/"
cd ..
```
Expected: `BUILD OK: assets under /view/`

- [ ] **Step 5: End-to-end serve check against an existing scene (GPU not required to view)**

Run (host has a `scenes/hires` from earlier work):
```bash
PORT=8080 timeout 6 python -m modules.serve &
sleep 2
curl -s -o /dev/null -w "view=%{http_code} scene=%{http_code}\n" "localhost:8080/view?scene=hires"
curl -s -o /dev/null -w "ply_json=%{http_code}\n" "localhost:8080/scenes/hires/scene.json"
```
Expected: `view=200` and `ply_json=200`.

- [ ] **Step 6: Commit**

```bash
git add web/vite.config.js web/src/main.js web/src/level.js
git commit -m "feat(viewer): production base /view/ + same-origin home & up-save links"
```

---

## Task 6: Dockerfile + .dockerignore

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Write `.dockerignore`** (keep the build context small — never ship local scenes/weights/builds)

`.dockerignore`:
```
.git
.venv
**/node_modules
web/dist
scenes
data
web/scenes
web/assets
web/orbit
**/__pycache__
*.pyc
docs
experiments
notebooks
```

- [ ] **Step 2: Write the multi-stage `Dockerfile`**

`Dockerfile`:
```dockerfile
# syntax=docker/dockerfile:1

# ---- Stage 1: build the Three.js viewer (base '/view/') ----
FROM node:20-slim AS viewer
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build          # -> /web/dist

# ---- Stage 2: CUDA runtime image (devel base: nvcc needed to build torch_scatter/pytorch3d) ----
FROM pytorch/pytorch:2.2.0-cuda12.1-cudnn8-devel
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PORT=8080
# Cover Ampere/Ada/Hopper so the compiled CUDA ops run on any of these GPUs.
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0"
RUN apt-get update && apt-get install -y --no-install-recommends \
      git build-essential ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# AnySplat deps first (heavy; torch already present in the base image).
COPY external_AnySplat/requirements.txt external_AnySplat/requirements.txt
RUN pip install --no-cache-dir -r external_AnySplat/requirements.txt
RUN pip install --no-cache-dir "flask>=3.0" "qrcode>=7.4"

# App code + the built viewer.
COPY . .
COPY --from=viewer /web/dist /app/web/dist
RUN pip install --no-cache-dir -e .

# Bake the AnySplat weights into the HF cache (build needs network; runtime does not).
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('lhjiang/anysplat')"
ENV HF_HUB_OFFLINE=1

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/healthz').status==200 else 1)"
CMD ["python", "-m", "modules.serve"]
```

> Note: `external_AnySplat/requirements.txt` pins `numpy==1.25.0` while `pyproject.toml` asks `numpy>=1.26`; pip resolves to the newer one at the `-e .` step. If an AnySplat import breaks on numpy, pin `numpy==1.26.*` in the requirements file. If `pytorch3d` (git build) is the slow/failing step, confirm it is actually imported by the reconstruct path before trimming it. Use the **build-error-resolver** agent for any build break — minimal fixes only.

- [ ] **Step 3: Build the image (long — AnySplat deps + weights)**

Run: `docker build -t splatial:dev .`
Expected: build completes; final line `naming to docker.io/library/splatial:dev`.

- [ ] **Step 4: Smoke-test the container WITHOUT a GPU (server must still boot + serve)**

Run:
```bash
docker run --rm -d --name splatial_smoke -p 8080:8080 splatial:dev
sleep 25
curl -s localhost:8080/healthz; echo
curl -s -o /dev/null -w "capture=%{http_code} view=%{http_code}\n" localhost:8080/ ; \
curl -s -o /dev/null -w "view=%{http_code}\n" localhost:8080/view
docker logs splatial_smoke | grep -i "on your phone" || true
docker rm -f splatial_smoke
```
Expected: `{"ok":true}`, `capture=200`, `view=200`, and the banner line is in the logs. (A "no CUDA GPU visible" warning is expected here — reconstruction is not exercised without `--gpus`.)

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat(docker): multi-stage CUDA image — viewer build, AnySplat deps, baked weights"
```

---

## Task 7: GHCR publish workflow

**Files:**
- Create: `.github/workflows/docker-publish.yml`

- [ ] **Step 1: Write the workflow** (builds + pushes a public image on a `v*` tag)

`.github/workflows/docker-publish.yml`:
```yaml
name: docker-publish
on:
  push:
    tags: ["v*"]
  workflow_dispatch:

jobs:
  build-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/metadata-action@v5
        id: meta
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=ref,event=tag
            type=raw,value=latest
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

- [ ] **Step 2: Verify the workflow YAML parses**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/docker-publish.yml')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docker-publish.yml
git commit -m "ci: publish Docker image to GHCR on version tags"
```

> After merge, the maintainer pushes a tag (`git tag v0.1.0 && git push origin v0.1.0`) to trigger the first build, then sets the GHCR package visibility to **Public** (one-time, in the repo's Packages settings) so HR needs no `docker login`. The GPU end-to-end acceptance test (Task 9) is run once locally on the GPU host.

---

## Task 8: README — "Run on your phone (Docker)" section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the section after "## How to run"**

Insert this block immediately after the existing `## How to run` fenced example in `README.md`:
```markdown
## Run on your phone (Docker)

Reconstruct and view from a phone with **one command** on any Linux machine with an NVIDIA GPU.

**One-time host setup:** install [Docker](https://docs.docker.com/engine/install/), the NVIDIA driver, and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

**Step 1 — start it (prints a URL + QR):**
```bash
docker run --gpus all --network host -v "$PWD/scenes:/app/scenes" ghcr.io/xji6xu4m3/splatial
```

**Step 2 — on your phone (same Wi-Fi):** scan the QR or open the printed `http://<host-ip>:8080`, record a room with your Camera app, upload it → it reconstructs (~1–2 min) → tap to view in 3D.

The view cap auto-scales to your GPU's VRAM (12 GB → 16 views, 24 GB → 32, ≥40 GB → 48); override with `-e MAX_VIEWS=24`. NVIDIA only (driver ≥ 525 for CUDA 12.1).
```

- [ ] **Step 2: Verify links/anchors render**

Run: `grep -n "Run on your phone (Docker)" README.md && grep -n "ghcr.io/xji6xu4m3/splatial" README.md`
Expected: both lines found.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): add one-command Docker phone-onboarding section"
```

---

## Task 9: Retire `tools/upload_server.py` + GPU acceptance test

**Files:**
- Delete: `tools/upload_server.py`
- Modify: `web/vite.config.js` comment referencing :8090 (optional clarity)

- [ ] **Step 1: Confirm nothing imports the old server**

Run: `grep -rn "upload_server" --include=*.py --include=*.md --include=*.yml . | grep -v node_modules`
Expected: only matches in docs/plans/specs (historical) — no code import. If a doc references how to run it, that's fine to leave.

- [ ] **Step 2: Delete the superseded server**

Run: `git rm tools/upload_server.py`

- [ ] **Step 3: Full test suite green**

Run: `pytest`
Expected: PASS (capture, scene_store, reconstruct smoke, and the new `modules/serve` tests).

- [ ] **Step 4: GPU acceptance test (run once on the GPU host)**

Run:
```bash
docker run --rm -d --gpus all --network host -v "$PWD/scenes:/app/scenes" --name splatial_acc ghcr.io/xji6xu4m3/splatial
sleep 30
# upload a short canned clip and poll to done
curl -s -F scene=docktest -F video=@data/room1.mp4 localhost:8080/upload >/dev/null
for i in $(seq 1 60); do s=$(curl -s localhost:8080/status/docktest | python -c "import sys,json;print(json.load(sys.stdin)['state'])"); echo "$s"; [ "$s" = "done" ] && break; [ "${s#error}" != "$s" ] && break; sleep 5; done
test -f scenes/docktest/scene.json && echo "RECON OK"
docker rm -f splatial_acc
```
Expected: status reaches `done` and `RECON OK` prints (a `scenes/docktest/scene.json` exists on the host via the volume mount). Then open `http://<host-ip>:8080/view?scene=docktest` on a phone and confirm the splats **draw** (visible room), per the viewer-render-verification rule.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(serve): retire tools/upload_server.py (superseded by modules.serve)"
```

---

## Self-Review notes (addressed)

- **Spec coverage:** §1 unified server → Tasks 3,5; §2 image+weights+VRAM autoscale+publish → Tasks 1,6,7; §3 networking+QR+two-steps → Tasks 2,4,8; §4 errors+testing → Tasks 3,4 (healthz, GPU-absent warning), 6,9 (smoke + acceptance). Persistence (volume) → Tasks 8,9.
- **No conda / no CORS** structural wins are realized in Task 3 (`subprocess_recon_launcher` uses `sys.executable`; all routes same-origin) and Task 5 (relative links).
- **Type/name consistency:** `default_max_views` (Task 1) used in Task 4; `create_app(...)` signature (Task 3) matches the Task-3 test and Task-4 call; `startup_banner(port)` (Task 2) matches Task-4 usage; viewer base `/view/` (Task 5) matches the `/view` routes (Task 3) and README/links.
- **Deviation from spec:** base image is `...-devel` (not `-runtime`) because `torch_scatter`/`pytorch3d` compile from source need `nvcc`; documented inline in Task 6.
```
