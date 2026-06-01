# Splatial Foundation (Phase 0 + Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a phone video of a small room into a renderable 3D Gaussian Splatting scene, and view it in a web viewer with a placed GLB object that stays anchored as the camera orbits.

**Architecture:** A Python pipeline (`capture` → `reconstruct`) produces a scene folder (`scene.ply` + JSON metadata + objects list) via the AnySplat feed-forward model. A web viewer (Three.js + `@mkkellogg/gaussian-splats-3d`) loads the scene folder over HTTP and renders the splat together with GLB meshes placed in the splat's coordinate frame. Shared JSON data contracts (`SplatScene`, `SceneObject`) are the only coupling between the Python and web sides.

**Tech Stack:** Python 3.10, PyTorch 2.x + CUDA (RTX 4070 Ti, 12 GB), OpenCV, AnySplat (`lhjiang/anysplat`, MIT), pytest; Vite + Three.js + `@mkkellogg/gaussian-splats-3d`, Playwright (smoke tests).

---

## File Structure

```
modules/
  capture/
    __init__.py
    frames.py            # extract_frames(video_path, out_dir, max_frames, long_side) -> list[Path]
    tests/test_frames.py
  scene_store/
    __init__.py
    contracts.py         # SplatScene, SceneObject, Transform dataclasses + (de)serialization
    store.py             # save_scene/load_scene/save_objects/load_objects on a scene folder
    tests/test_contracts.py
    tests/test_store.py
  reconstruct/
    __init__.py
    anysplat_provider.py # AnySplatReconstructor: frames -> SplatScene (+ scene.ply)
    cli.py               # python -m modules.reconstruct.cli <video> <scene_dir>
    tests/test_provider_smoke.py
web/
  index.html
  package.json
  vite.config.js
  src/
    main.js              # bootstrap viewer
    sceneLoader.js       # fetch SplatScene + SceneObject JSON
    splatViewer.js       # GaussianSplats3D viewer + add GLB objects
  tests/viewer.spec.js   # Playwright smoke test
scenes/                  # runtime output (gitignored): scenes/<id>/{scene.ply,scene.json,objects.json}
assets/                  # GLB library (e.g. assets/chair.glb)
pyproject.toml           # python deps + pytest config
```

**Shared data contracts (authored once in `contracts.py`, mirrored in JSON the viewer reads):**

```
SplatScene  { "id": str, "ply": "scene.ply", "bbox": [[minx,miny,minz],[maxx,maxy,maxz]],
              "up": [x,y,z], "scale_hint": float, "source_meta": { ... } }
Transform   { "position": [x,y,z], "rotation": [x,y,z,w], "scale": [x,y,z] }   # rotation = quaternion
SceneObject { "id": str, "glb": str, "transform": Transform,
              "material_overrides": { "color"?: [r,g,b] }, "scene_id": str }
```

A scene folder is the unit of exchange: `scenes/<id>/scene.ply`, `scenes/<id>/scene.json` (SplatScene), `scenes/<id>/objects.json` (list of SceneObject).

---

## Task 0: Project environment & scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `modules/__init__.py`, `modules/capture/__init__.py`, `modules/scene_store/__init__.py`, `modules/reconstruct/__init__.py`
- Create: `scenes/.gitkeep`, `assets/.gitkeep`

- [ ] **Step 1: Create the Python package config**

Create `pyproject.toml`:

```toml
[project]
name = "splatial"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "numpy>=1.26",
    "opencv-python>=4.9",
    "pillow>=10.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["modules"]
addopts = "-q"
```

- [ ] **Step 2: Create empty package files**

```bash
mkdir -p modules/capture/tests modules/scene_store/tests modules/reconstruct/tests scenes assets
touch modules/__init__.py modules/capture/__init__.py modules/scene_store/__init__.py modules/reconstruct/__init__.py
touch modules/capture/tests/__init__.py modules/scene_store/tests/__init__.py modules/reconstruct/tests/__init__.py
touch scenes/.gitkeep assets/.gitkeep
```

- [ ] **Step 3: Create the venv and install dev deps**

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```
Expected: installs numpy, opencv, pillow, pytest without error.

- [ ] **Step 4: Verify pytest runs (collects 0 tests)**

Run: `. .venv/bin/activate && pytest`
Expected: `no tests ran` (exit 0) — confirms config is valid.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml modules scenes/.gitkeep assets/.gitkeep
git commit -m "chore: scaffold python package + module dirs"
```

---

## Task 1: `capture` — extract frames from a phone video

**Files:**
- Create: `modules/capture/frames.py`
- Test: `modules/capture/tests/test_frames.py`

- [ ] **Step 1: Write the failing test**

`modules/capture/tests/test_frames.py`:

```python
import numpy as np
import cv2
from pathlib import Path
from modules.capture.frames import resize_long_side, pick_frame_indices


def test_resize_long_side_caps_longest_dimension():
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)  # H, W
    out = resize_long_side(img, 448)
    h, w = out.shape[:2]
    assert max(h, w) == 448
    assert abs((w / h) - (1920 / 1080)) < 0.02  # aspect preserved


def test_pick_frame_indices_uniform_and_capped():
    idx = pick_frame_indices(total=100, max_frames=8)
    assert len(idx) == 8
    assert idx[0] == 0 and idx[-1] == 99
    assert idx == sorted(idx) and len(set(idx)) == 8


def test_pick_frame_indices_fewer_than_max():
    idx = pick_frame_indices(total=5, max_frames=8)
    assert idx == [0, 1, 2, 3, 4]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest modules/capture/tests/test_frames.py -v`
Expected: FAIL — `ImportError: cannot import name 'resize_long_side'`.

- [ ] **Step 3: Implement the pure helpers**

`modules/capture/frames.py`:

```python
from pathlib import Path
import cv2
import numpy as np


def resize_long_side(img: np.ndarray, long_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = long_side / max(h, w)
    if scale >= 1.0:
        return img
    new_w, new_h = round(w * scale), round(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def pick_frame_indices(total: int, max_frames: int) -> list[int]:
    if total <= max_frames:
        return list(range(total))
    step = (total - 1) / (max_frames - 1)
    return [round(i * step) for i in range(max_frames)]
```

- [ ] **Step 4: Run the helper tests to confirm they pass**

Run: `pytest modules/capture/tests/test_frames.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Add the integration function (uses the helpers)**

Append to `modules/capture/frames.py`:

```python
def extract_frames(video_path: str, out_dir: str, max_frames: int = 16,
                   long_side: int = 448) -> list[Path]:
    """Sample up to `max_frames` uniformly-spaced frames from a video, resize so the
    longest side <= `long_side`, write PNGs to out_dir. Returns the written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    wanted = set(pick_frame_indices(total, max_frames)) if total else set()
    written: list[Path] = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if not wanted or i in wanted:
            frame = resize_long_side(frame, long_side)
            p = out / f"frame_{len(written):04d}.png"
            cv2.imwrite(str(p), frame)
            written.append(p)
        i += 1
    cap.release()
    if not written:
        raise RuntimeError("no frames extracted")
    return written
```

- [ ] **Step 6: Write an integration test using a synthetic video**

Append to `modules/capture/tests/test_frames.py`:

```python
def test_extract_frames_writes_capped_resized_pngs(tmp_path):
    vid = tmp_path / "clip.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(vid), fourcc, 10.0, (640, 480))
    for k in range(30):
        vw.write(np.full((480, 640, 3), k * 5 % 255, dtype=np.uint8))
    vw.release()

    from modules.capture.frames import extract_frames
    paths = extract_frames(str(vid), str(tmp_path / "frames"), max_frames=8, long_side=320)
    assert len(paths) == 8
    img = cv2.imread(str(paths[0]))
    assert max(img.shape[:2]) == 320
```

- [ ] **Step 7: Run all capture tests**

Run: `pytest modules/capture -v`
Expected: PASS (4 passed). If the synthetic-video test fails to open the writer, install codecs: `pip install opencv-python` is usually enough; otherwise mark it `@pytest.mark.skipif` on `cv2.VideoWriter` failure and rely on the helper tests.

- [ ] **Step 8: Commit**

```bash
git add modules/capture
git commit -m "feat(capture): uniform frame sampling + resize from phone video"
```

---

## Task 2: `scene_store` — data contracts + persistence

**Files:**
- Create: `modules/scene_store/contracts.py`
- Create: `modules/scene_store/store.py`
- Test: `modules/scene_store/tests/test_contracts.py`, `modules/scene_store/tests/test_store.py`

- [ ] **Step 1: Write the failing contracts test**

`modules/scene_store/tests/test_contracts.py`:

```python
from modules.scene_store.contracts import SplatScene, SceneObject, Transform


def test_transform_roundtrip():
    t = Transform(position=[1, 2, 3], rotation=[0, 0, 0, 1], scale=[1, 1, 1])
    assert Transform.from_dict(t.to_dict()) == t


def test_splatscene_roundtrip():
    s = SplatScene(id="room1", ply="scene.ply",
                   bbox=[[0, 0, 0], [1, 1, 1]], up=[0, 1, 0],
                   scale_hint=1.0, source_meta={"frames": 16})
    assert SplatScene.from_dict(s.to_dict()) == s


def test_sceneobject_roundtrip():
    o = SceneObject(id="o1", glb="assets/chair.glb",
                    transform=Transform([0, 0, 0], [0, 0, 0, 1], [1, 1, 1]),
                    material_overrides={"color": [1.0, 0.0, 0.0]}, scene_id="room1")
    assert SceneObject.from_dict(o.to_dict()) == o
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest modules/scene_store/tests/test_contracts.py -v`
Expected: FAIL — `ModuleNotFoundError: modules.scene_store.contracts`.

- [ ] **Step 3: Implement the contracts**

`modules/scene_store/contracts.py`:

```python
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class Transform:
    position: list[float]
    rotation: list[float]   # quaternion [x, y, z, w]
    scale: list[float]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Transform":
        return Transform(position=list(d["position"]),
                         rotation=list(d["rotation"]),
                         scale=list(d["scale"]))


@dataclass
class SplatScene:
    id: str
    ply: str
    bbox: list[list[float]]
    up: list[float]
    scale_hint: float
    source_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SplatScene":
        return SplatScene(id=d["id"], ply=d["ply"], bbox=d["bbox"],
                          up=d["up"], scale_hint=d["scale_hint"],
                          source_meta=d.get("source_meta", {}))


@dataclass
class SceneObject:
    id: str
    glb: str
    transform: Transform
    material_overrides: dict
    scene_id: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["transform"] = self.transform.to_dict()
        return d

    @staticmethod
    def from_dict(d: dict) -> "SceneObject":
        return SceneObject(id=d["id"], glb=d["glb"],
                           transform=Transform.from_dict(d["transform"]),
                           material_overrides=d.get("material_overrides", {}),
                           scene_id=d["scene_id"])
```

- [ ] **Step 4: Run contracts test to confirm pass**

Run: `pytest modules/scene_store/tests/test_contracts.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Write the failing store test**

`modules/scene_store/tests/test_store.py`:

```python
from modules.scene_store.contracts import SplatScene, SceneObject, Transform
from modules.scene_store.store import scene_dir, save_scene, load_scene, save_objects, load_objects


def test_save_and_load_scene(tmp_path):
    s = SplatScene(id="room1", ply="scene.ply", bbox=[[0, 0, 0], [1, 1, 1]],
                   up=[0, 1, 0], scale_hint=1.0, source_meta={})
    save_scene(tmp_path, s)
    assert (scene_dir(tmp_path, "room1") / "scene.json").exists()
    assert load_scene(tmp_path, "room1") == s


def test_save_and_load_objects(tmp_path):
    s = SplatScene(id="room1", ply="scene.ply", bbox=[[0, 0, 0], [1, 1, 1]],
                   up=[0, 1, 0], scale_hint=1.0, source_meta={})
    save_scene(tmp_path, s)
    objs = [SceneObject("o1", "assets/chair.glb",
                        Transform([0, 0, 0], [0, 0, 0, 1], [1, 1, 1]), {}, "room1")]
    save_objects(tmp_path, "room1", objs)
    assert load_objects(tmp_path, "room1") == objs
```

- [ ] **Step 6: Run it to confirm it fails**

Run: `pytest modules/scene_store/tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: modules.scene_store.store`.

- [ ] **Step 7: Implement the store**

`modules/scene_store/store.py`:

```python
import json
from pathlib import Path
from .contracts import SplatScene, SceneObject


def scene_dir(root, scene_id: str) -> Path:
    d = Path(root) / scene_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_scene(root, scene: SplatScene) -> Path:
    d = scene_dir(root, scene.id)
    p = d / "scene.json"
    p.write_text(json.dumps(scene.to_dict(), indent=2))
    return p


def load_scene(root, scene_id: str) -> SplatScene:
    p = scene_dir(root, scene_id) / "scene.json"
    return SplatScene.from_dict(json.loads(p.read_text()))


def save_objects(root, scene_id: str, objects: list[SceneObject]) -> Path:
    p = scene_dir(root, scene_id) / "objects.json"
    p.write_text(json.dumps([o.to_dict() for o in objects], indent=2))
    return p


def load_objects(root, scene_id: str) -> list[SceneObject]:
    p = scene_dir(root, scene_id) / "objects.json"
    if not p.exists():
        return []
    return [SceneObject.from_dict(x) for x in json.loads(p.read_text())]
```

- [ ] **Step 8: Run all scene_store tests**

Run: `pytest modules/scene_store -v`
Expected: PASS (5 passed).

- [ ] **Step 9: Commit**

```bash
git add modules/scene_store
git commit -m "feat(scene_store): SplatScene/SceneObject contracts + folder persistence"
```

---

## Task 3: `reconstruct` — AnySplat provider (frames → scene.ply)

> AnySplat is a third-party model. **Pin its real inference API before coding the adapter** (Step 1) rather than guessing. Our adapter's own interface (below) is fixed; only the inner AnySplat call is filled in from the repo's example.

**Files:**
- Create: `modules/reconstruct/anysplat_provider.py`
- Create: `modules/reconstruct/cli.py`
- Test: `modules/reconstruct/tests/test_provider_smoke.py`
- Modify: `pyproject.toml` (add a `recon` extra)

- [ ] **Step 1: Install AnySplat and read its inference example**

```bash
. .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install git+https://github.com/InternRobotics/AnySplat.git
python -c "import torch; print('cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```
Expected: `cuda True NVIDIA GeForce RTX 4070 Ti`.
Then open the repo's README / `demo`/`example` script and note the exact: (a) how the model is loaded from `lhjiang/anysplat`, (b) the function that takes a list of image paths/tensors and returns Gaussians + camera params, (c) the helper that exports Gaussians to a `.ply`. Record these in a comment at the top of `anysplat_provider.py`.

- [ ] **Step 2: Define the adapter interface (our fixed contract)**

`modules/reconstruct/anysplat_provider.py`:

```python
"""AnySplat reconstruction adapter.

Fill the AnySplat calls in `_run_anysplat` / `_export_ply` from the repo example
(pinned in Task 3 Step 1). Everything else here is our stable contract.
"""
from pathlib import Path
import numpy as np
from modules.scene_store.contracts import SplatScene


class AnySplatReconstructor:
    def __init__(self, device: str = "cuda", long_side: int = 448, max_views: int = 16):
        self.device = device
        self.long_side = long_side
        self.max_views = max_views
        self._model = None

    def _load(self):
        if self._model is None:
            # e.g. from anysplat import AnySplat; self._model = AnySplat.from_pretrained("lhjiang/anysplat").to(self.device)
            from anysplat import AnySplat  # exact import per repo example
            self._model = AnySplat.from_pretrained("lhjiang/anysplat").to(self.device)
        return self._model

    def _run_anysplat(self, image_paths: list[Path]):
        """Return (gaussians, cameras) from AnySplat for the given images."""
        model = self._load()
        # exact call per repo example; images capped to self.max_views, resized to long_side
        return model.run(image_paths)  # placeholder name -> replace with the real entrypoint

    def _export_ply(self, gaussians, out_ply: Path) -> None:
        """Write standard 3DGS .ply (INRIA format) for the web splat renderer."""
        # use the repo's export util, e.g. gaussians.save_ply(str(out_ply))
        gaussians.save_ply(str(out_ply))

    def reconstruct(self, image_paths: list[Path], scene_id: str, out_ply: Path) -> SplatScene:
        capped = image_paths[: self.max_views]
        gaussians, cameras = self._run_anysplat(capped)
        self._export_ply(gaussians, out_ply)
        xyz = self._gaussian_xyz(gaussians)          # (N,3) numpy
        bbox = [xyz.min(0).tolist(), xyz.max(0).tolist()]
        return SplatScene(
            id=scene_id, ply=out_ply.name, bbox=bbox,
            up=[0.0, 1.0, 0.0], scale_hint=1.0,
            source_meta={"model": "anysplat", "n_views": len(capped),
                         "n_gaussians": int(xyz.shape[0])},
        )

    @staticmethod
    def _gaussian_xyz(gaussians) -> np.ndarray:
        # adapt to the repo's gaussian container (e.g. gaussians.means.cpu().numpy())
        return np.asarray(gaussians.means.detach().cpu().numpy())
```

- [ ] **Step 3: Write the CLI**

`modules/reconstruct/cli.py`:

```python
import sys
from pathlib import Path
from modules.capture.frames import extract_frames
from modules.scene_store.store import save_scene, scene_dir
from modules.reconstruct.anysplat_provider import AnySplatReconstructor


def main():
    if len(sys.argv) != 4:
        print("usage: python -m modules.reconstruct.cli <video> <scenes_root> <scene_id>")
        sys.exit(2)
    video, scenes_root, scene_id = sys.argv[1], sys.argv[2], sys.argv[3]
    d = scene_dir(scenes_root, scene_id)
    frames = extract_frames(video, str(d / "frames"), max_frames=16, long_side=448)
    print(f"extracted {len(frames)} frames")
    recon = AnySplatReconstructor()
    scene = recon.reconstruct(frames, scene_id, d / "scene.ply")
    save_scene(scenes_root, scene)
    print(f"wrote {d/'scene.ply'} with {scene.source_meta['n_gaussians']} gaussians")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write a smoke test that mocks AnySplat (no GPU needed in CI)**

`modules/reconstruct/tests/test_provider_smoke.py`:

```python
import numpy as np
from pathlib import Path
from modules.reconstruct.anysplat_provider import AnySplatReconstructor


class _FakeGaussians:
    means = type("M", (), {"detach": lambda self: self,
                            "cpu": lambda self: self,
                            "numpy": lambda self: np.random.rand(100, 3)})()

    def save_ply(self, p):
        Path(p).write_text("ply\nfake\n")


def test_reconstruct_builds_scene(tmp_path, monkeypatch):
    r = AnySplatReconstructor()
    monkeypatch.setattr(r, "_run_anysplat", lambda paths: (_FakeGaussians(), None))
    out = tmp_path / "scene.ply"
    scene = r.reconstruct([Path("a.png"), Path("b.png")], "room1", out)
    assert out.exists()
    assert scene.id == "room1"
    assert scene.source_meta["n_gaussians"] == 100
    assert len(scene.bbox) == 2 and len(scene.bbox[0]) == 3
```

- [ ] **Step 5: Run the smoke test**

Run: `pytest modules/reconstruct/tests/test_provider_smoke.py -v`
Expected: PASS (1 passed) — verifies our adapter wiring independent of the real model.

- [ ] **Step 6: Wire the real AnySplat calls and fix placeholders**

Using the API pinned in Step 1, replace the placeholder lines in `_load`, `_run_anysplat`, `_export_ply`, and `_gaussian_xyz` with the repo's real entrypoints. Apply the 12 GB flags before importing torch-heavy modules:

```python
import os
os.environ.setdefault("ATTN_BACKEND", "xformers")
os.environ.setdefault("SPCONV_ALGO", "native")
```
Add `import torch; torch.cuda.empty_cache()` at the end of `_run_anysplat`.

- [ ] **Step 7: Commit**

```bash
git add modules/reconstruct pyproject.toml
git commit -m "feat(reconstruct): AnySplat adapter + CLI (frames -> scene.ply)"
```

---

## Task 4: Phase 0 exit — reconstruct a real room (integration)

**Files:** none (operational milestone).

- [ ] **Step 1: Record a short phone video of a small room**

Slow, smooth sweep, ~15–20s, good lighting, plenty of overlap, cover one corner + the floor. Copy to `data/room1.mp4` (gitignored).

- [ ] **Step 2: Run the pipeline on the GPU**

```bash
. .venv/bin/activate
python -m modules.reconstruct.cli data/room1.mp4 scenes room1
```
Expected: prints `extracted 16 frames` then `wrote scenes/room1/scene.ply with <N> gaussians`. Watch `nvidia-smi -l 1` in another terminal — confirm peak VRAM < ~11 GB.

- [ ] **Step 3: If it OOMs, reduce load**

Lower caps in the CLI call path: `max_frames=8`, `long_side=384`. Re-run. If still OOM, document the cloud-GPU fallback (rent an A10/L4, same command) in `modules/reconstruct/README.md`.

- [ ] **Step 4: Sanity-check the .ply**

```bash
python -c "p=open('scenes/room1/scene.ply','rb').read(200); print(p[:200])"
ls -la scenes/room1/
```
Expected: a binary/ascii PLY header; `scene.json` present. Record actual VRAM + runtime + chosen caps in `modules/reconstruct/README.md`.

- [ ] **Step 5: Commit the notes (not the data)**

```bash
git add modules/reconstruct/README.md
git commit -m "docs(reconstruct): record real-room VRAM/runtime + capture guidance"
```

---

## Task 5: Web viewer — render the splat

**Files:**
- Create: `web/package.json`, `web/vite.config.js`, `web/index.html`
- Create: `web/src/main.js`, `web/src/splatViewer.js`

- [ ] **Step 1: Initialize the web app**

```bash
cd web
npm init -y
npm install three @mkkellogg/gaussian-splats-3d
npm install -D vite @playwright/test
```

- [ ] **Step 2: Create `web/vite.config.js`**

```js
import { defineConfig } from 'vite'
export default defineConfig({
  server: { port: 5173, fs: { allow: ['..'] } },  // allow serving ../scenes
})
```

- [ ] **Step 3: Create `web/index.html`**

```html
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Splatial</title>
    <style>html,body,#app{margin:0;height:100%;width:100%;overflow:hidden}</style>
  </head>
  <body><div id="app"></div><script type="module" src="/src/main.js"></script></body>
</html>
```

- [ ] **Step 4: Create `web/src/splatViewer.js`**

```js
import * as GaussianSplats3D from '@mkkellogg/gaussian-splats-3d'
import * as THREE from 'three'

export async function createViewer(container, plyUrl) {
  const viewer = new GaussianSplats3D.Viewer({
    rootElement: container,
    cameraUp: [0, 1, 0],
    initialCameraPosition: [0, 0, 4],
    initialCameraLookAt: [0, 0, 0],
    sphericalHarmonicsDegree: 0,
  })
  await viewer.addSplatScene(plyUrl, { showLoadingUI: true })
  viewer.start()
  return viewer  // viewer.threeScene is the THREE.Scene we add objects to
}
```

- [ ] **Step 5: Create `web/src/main.js`**

```js
import { createViewer } from './splatViewer.js'

const app = document.getElementById('app')
const params = new URLSearchParams(location.search)
const sceneId = params.get('scene') || 'room1'
const plyUrl = `/scenes/${sceneId}/scene.ply`

createViewer(app, plyUrl).then((viewer) => {
  window.__viewer = viewer  // exposed for the Playwright smoke test
}).catch((e) => { console.error('viewer failed', e) })
```

- [ ] **Step 6: Serve scenes to the dev server**

```bash
# from repo root, symlink scenes into web so Vite serves /scenes/...
ln -s ../scenes web/scenes 2>/dev/null || true
```
Add `web/scenes` to `.gitignore`.

- [ ] **Step 7: Run it and verify visually**

```bash
cd web && npm run dev -- --host
```
(If `npm run dev` is missing, add `"scripts": {"dev":"vite","build":"vite build","preview":"vite preview"}` to `web/package.json`.)
Open `http://localhost:5173/?scene=room1`. Expected: the reconstructed room renders as a splat; mouse drag orbits.

- [ ] **Step 8: Commit**

```bash
git add web/package.json web/package-lock.json web/vite.config.js web/index.html web/src .gitignore
git commit -m "feat(viewer): web Three.js Gaussian-splat viewer renders scene.ply"
```

---

## Task 6: `objects` — place a GLB anchored in the splat frame

**Files:**
- Create: `web/src/sceneLoader.js`
- Create: `web/src/objects.js`
- Modify: `web/src/main.js`
- Add: a GLB to `assets/` (e.g. `assets/chair.glb` from Poly Haven, CC0)

- [ ] **Step 1: Add a GLB asset and serve it**

Download a small CC0 chair GLB to `assets/chair.glb`. Symlink for the dev server:
```bash
ln -s ../assets web/assets 2>/dev/null || true
```
Add `web/assets` to `.gitignore`.

- [ ] **Step 2: Create `web/src/sceneLoader.js`**

```js
export async function loadSceneMeta(sceneId) {
  const scene = await fetch(`/scenes/${sceneId}/scene.json`).then(r => r.json())
  const objects = await fetch(`/scenes/${sceneId}/objects.json`)
    .then(r => r.ok ? r.json() : [])
    .catch(() => [])
  return { scene, objects }
}
```

- [ ] **Step 3: Create `web/src/objects.js`**

```js
import * as THREE from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

const loader = new GLTFLoader()

export function loadGLB(url) {
  return new Promise((res, rej) => loader.load(url, (g) => res(g.scene), undefined, rej))
}

export function applyTransform(obj3d, t) {
  obj3d.position.fromArray(t.position)
  obj3d.quaternion.fromArray(t.rotation)   // [x,y,z,w]
  obj3d.scale.fromArray(t.scale)
}

export async function placeObject(threeScene, sceneObject) {
  const root = await loadGLB(sceneObject.glb)
  applyTransform(root, sceneObject.transform)
  if (sceneObject.material_overrides?.color) {
    const [r, g, b] = sceneObject.material_overrides.color
    root.traverse((m) => { if (m.isMesh) m.material = new THREE.MeshStandardMaterial({ color: new THREE.Color(r, g, b) }) })
  }
  root.userData.objectId = sceneObject.id
  threeScene.add(root)
  return root
}
```

- [ ] **Step 4: Wire objects into `web/src/main.js`**

Replace `web/src/main.js` with:

```js
import { createViewer } from './splatViewer.js'
import { loadSceneMeta } from './sceneLoader.js'
import { placeObject } from './objects.js'
import * as THREE from 'three'

const app = document.getElementById('app')
const sceneId = new URLSearchParams(location.search).get('scene') || 'room1'

const { scene, objects } = await loadSceneMeta(sceneId)
const viewer = await createViewer(app, `/scenes/${sceneId}/${scene.ply}`)
viewer.threeScene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 1.2))
for (const o of objects) {
  // GLB paths in objects.json are repo-relative (e.g. assets/chair.glb) -> serve as /assets/...
  await placeObject(viewer.threeScene, { ...o, glb: '/' + o.glb })
}
window.__viewer = viewer
window.__objectCount = objects.length
```
(If top-level `await` errors, wrap the body in an `async function boot(){...}; boot()`.)

- [ ] **Step 5: Create a test objects.json by hand**

`scenes/room1/objects.json` (place the chair near the scene origin / on the floor; adjust `position[1]` to the floor height seen in the viewer):

```json
[{"id":"o1","glb":"assets/chair.glb",
  "transform":{"position":[0,0,0],"rotation":[0,0,0,1],"scale":[1,1,1]},
  "material_overrides":{},"scene_id":"room1"}]
```

- [ ] **Step 6: Verify the object renders and stays anchored**

Reload `http://localhost:5173/?scene=room1`. Expected: the chair appears in the splat; **orbit the camera — the chair stays fixed relative to the room** (same coordinate frame). Adjust `position`/`scale` in `objects.json` until the chair sits sensibly on the floor.

- [ ] **Step 7: Commit**

```bash
git add web/src .gitignore
git commit -m "feat(objects): load + place GLB anchored in the splat coordinate frame"
```

---

## Task 7: Phase 1 exit — Playwright smoke test + green run

**Files:**
- Create: `web/tests/viewer.spec.js`
- Create: `web/playwright.config.js`

- [ ] **Step 1: Create `web/playwright.config.js`**

```js
import { defineConfig } from '@playwright/test'
export default defineConfig({
  webServer: { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true },
  use: { baseURL: 'http://localhost:5173' },
})
```

- [ ] **Step 2: Write the smoke test**

`web/tests/viewer.spec.js`:

```js
import { test, expect } from '@playwright/test'

test('viewer loads splat + object without console errors', async ({ page }) => {
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto('/?scene=room1')
  await page.waitForFunction(() => window.__viewer !== undefined, { timeout: 30000 })
  const count = await page.evaluate(() => window.__objectCount)
  expect(count).toBeGreaterThanOrEqual(1)
  const canvas = page.locator('canvas')
  await expect(canvas.first()).toBeVisible()
  expect(errors, errors.join('\n')).toHaveLength(0)
})
```

- [ ] **Step 3: Run the smoke test**

```bash
cd web && npx playwright install chromium && npx playwright test
```
Expected: 1 passed (requires `scenes/room1/` from Task 4 + `objects.json` from Task 6).

- [ ] **Step 4: Run the full Python suite**

Run: `cd .. && . .venv/bin/activate && pytest`
Expected: all green (capture + scene_store + reconstruct smoke).

- [ ] **Step 5: Add the per-module READMEs**

Create one-paragraph `README.md` in each of `modules/capture`, `modules/scene_store`, `modules/reconstruct`, and `web/` documenting the public API + data contract (the function signatures and the `SplatScene`/`SceneObject` JSON shape from this plan).

- [ ] **Step 6: Commit**

```bash
git add web/tests web/playwright.config.js modules/*/README.md web/README.md
git commit -m "test(viewer): playwright smoke + per-module API docs (Phase 1 exit)"
```

---

## Phase 1 Exit Criteria (Definition of Done)

- `python -m modules.reconstruct.cli data/room1.mp4 scenes room1` produces `scenes/room1/scene.ply` on the 4070 Ti within VRAM.
- `http://localhost:5173/?scene=room1` renders the room splat with a chair that **stays anchored as you orbit**.
- `pytest` green; `npx playwright test` green.
- Each module has a README documenting its API + the shared data contracts.

## Out of scope (next plans)

- Phase 2 — object editing (recolor/swap/move via `editor`).
- Phase 3 — voice→3D generation (`generate`: Web Speech API → SDXL-Turbo → TRELLIS, pre-gen cache).
- Phase 4 — real-scene editing (Gaussian Grouping pre-baked variants).
- Phase 5 — hardening, full dry-run; later: Meta/Quest port, camera-only glasses track.
