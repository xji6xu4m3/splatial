"""Apply the patches needed to run AnySplat's post-optimization on a 12 GB GPU.

The AnySplat repo (cloned to external_AnySplat/, gitignored) is research code with a few
import/memory issues for our setup. This script applies them idempotently so post-opt is
reproducible from a fresh clone:

  1. colmap.py: make `from pycolmap import SceneManager` optional (the COLMAP Parser is
     unused — the trainer is camera-free), and fix `from normalize import` -> relative.
  2. simple_trainer.py: wrap the initial `model.encoder(...)` call in `torch.no_grad()`
     so the encoder graph isn't retained (the original OOMs the voxelization on 12 GB).

Run:  python tools/patch_anysplat.py [path-to-external_AnySplat]
Also install the extra deps in the anysplat env:
  tyro tensorboard pycolmap viser nerfview splines tensorly  + fused_ssim (CUDA build)
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "external_AnySplat"


def patch(path: Path, old: str, new: str, tag: str) -> None:
    s = path.read_text()
    if new in s:
        print(f"[skip] {tag} already applied")
        return
    if old not in s:
        print(f"[WARN] {tag}: pattern not found in {path}")
        return
    path.write_text(s.replace(old, new, 1))
    print(f"[ok]   {tag}")


colmap = ROOT / "src/post_opt/datasets/colmap.py"
patch(colmap,
      "from pycolmap import SceneManager",
      "try:\n    from pycolmap import SceneManager\nexcept Exception:\n    SceneManager = None  # patched: COLMAP Parser unused (camera-free post-opt)",
      "colmap: optional pycolmap")
patch(colmap,
      "from normalize import (",
      "from .normalize import (",
      "colmap: relative normalize import")

trainer = ROOT / "src/post_opt/simple_trainer.py"
patch(trainer,
      "        encoder_output = model.encoder(\n            ctx_images,\n            global_step=0,\n            visualization_dump={},\n        )",
      "        with torch.no_grad():  # patched: inference-only init; avoids retaining encoder graph (OOM on 12GB)\n            encoder_output = model.encoder(\n                ctx_images,\n                global_step=0,\n                visualization_dump={},\n            )",
      "trainer: no_grad encoder init")

print("done.")
