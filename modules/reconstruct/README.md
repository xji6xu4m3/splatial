# modules/reconstruct

Converts a list of image frames into a 3D Gaussian Splatting scene file (`scene.ply`) and returns a `SplatScene` data contract. Supports two interchangeable engines selected via the `RECON_ENGINE` environment variable.

## Public API

### `AnySplatReconstructor` (`anysplat_provider.py`)

Feed-forward reconstruction using the AnySplat model (`lhjiang/anysplat`). All heavy imports (`torch`, `anysplat`) are lazy — deferred inside `_load()` so the module imports cleanly without GPU packages installed.

```python
from modules.reconstruct.anysplat_provider import AnySplatReconstructor

r = AnySplatReconstructor(device="cuda", long_side=448, max_views=16)
scene: SplatScene = r.reconstruct(
    image_paths=[Path("frame_0000.png"), ...],
    scene_id="room1",
    out_ply=Path("scenes/room1/scene.ply"),
)
```

### `VGGTReconstructor` (`vggt_provider.py`)

Per-scene optimization fallback using VGGT-1B-Commercial for poses/depth/pointmaps and `gsplat` for 3DGS optimization. All heavy imports are lazy. `_run_vggt` and `_optimize_gsplat` contain `TODO-PIN` markers to be filled from the repo examples before use.

```python
from modules.reconstruct.vggt_provider import VGGTReconstructor

r = VGGTReconstructor(device="cuda", long_side=448, max_views=16, opt_steps=2000)
scene: SplatScene = r.reconstruct(image_paths, scene_id, out_ply)
```

### `make_reconstructor(engine)` (`factory.py`)

Returns the correct reconstructor instance for the given engine name. Raises `ValueError` for unknown engines.

```python
from modules.reconstruct.factory import make_reconstructor

recon = make_reconstructor("anysplat")   # or "vggt"
# RECON_ENGINE env var is read by cli.py; pass it explicitly here
```

### CLI (`cli.py`)

```
python -m modules.reconstruct.cli <video> <scenes_root> <scene_id>
RECON_ENGINE=vggt python -m modules.reconstruct.cli data/room1.mp4 scenes room1
```

Extracts up to 16 frames from the video, runs the chosen engine, writes `scenes/<scene_id>/scene.ply` and `scenes/<scene_id>/scene.json`.

## Fallback trigger (AnySplat → VGGT)

Switch to `RECON_ENGINE=vggt` if any of:
- AnySplat fails to install or import on the target machine.
- Peak VRAM > ~11 GB (or OOM) on 12 GB GPU even after reducing to `max_frames=8, long_side=384`.
- AnySplat output quality is visibly broken (floaters, holes, smeared geometry).

Document the chosen engine and reason in this file after the real-room run (Task 4).

## Shared Data Contracts

Both engines return a `SplatScene` (from `modules.scene_store.contracts`):

```json
{
  "id": "room1",
  "ply": "scene.ply",
  "bbox": [[-1.0, -0.5, -1.0], [1.0, 1.5, 1.0]],
  "up": [0.0, 1.0, 0.0],
  "scale_hint": 1.0,
  "source_meta": {
    "model": "anysplat",
    "n_views": 16,
    "n_gaussians": 250000
  }
}
```

The scene folder written by the CLI:
```
scenes/<id>/
  scene.ply       # standard INRIA 3DGS binary/ascii PLY
  scene.json      # SplatScene serialized
  frames/         # extracted input frames (intermediate)
```

## Tests

```bash
. .venv/bin/activate
pytest modules/reconstruct -v
```

All tests use monkeypatching — no GPU, torch, anysplat, or vggt packages required.

## Verified install & run (RTX 4070 Ti, 12 GB — 2026-06-01)

**Engine chosen: AnySplat** (the VGGT fallback was NOT needed). Peak VRAM **~6.1 GB** for 16 views @ 448px → **1.66M Gaussians**, `scene.ply` ~113 MB. `RECON_ENGINE=anysplat`.

Install lives in a dedicated **conda env `anysplat` (Python 3.10)** so AnySplat's prebuilt cp310 wheels apply:
- `torch==2.2.0 torchvision==0.17.0 --index-url .../cu121`, pin **numpy==1.26.4** (torch 2.2 needs numpy<2).
- Prebuilt wheels: `torch_scatter==2.1.2` (data.pyg.org), `gsplat 1.4.0` (cp310/pt22cu121 release wheel).
- **pytorch3d 0.7.8 built from source** (no prebuilt wheel exists): `pip install --no-build-isolation git+https://github.com/facebookresearch/pytorch3d.git@stable` with `CUDA_HOME` = a full CUDA 12.x toolkit, `CPATH=$CUDA_HOME/targets/x86_64-linux/include` (conda-CUDA header layout), `TORCH_CUDA_ARCH_LIST=8.9` (Ada), and the **anysplat env's python first on PATH** so the wheel builds cp310.
- Clone AnySplat to `external_AnySplat/`; point the provider at it via `ANYSPLAT_ROOT`.

Run:
```bash
conda run -n anysplat env ANYSPLAT_ROOT=$PWD/external_AnySplat RECON_ENGINE=anysplat \
  python -m modules.reconstruct.cli data/room1.mp4 scenes room1
```
