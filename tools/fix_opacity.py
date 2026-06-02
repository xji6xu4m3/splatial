"""Repair AnySplat-exported .ply files whose opacity was stored as a LINEAR probability.

The web viewer (and the standard 3DGS .ply convention) applies sigmoid() to the stored
opacity on load. AnySplat's export_ply wrote a linear [0,1] value, so everything rendered
at alpha sigmoid([0,1]) = 0.50..0.73 — no solid surfaces, no invisible splats (see-through
+ ghost haze). This rewrites opacity as logit(opacity) so the viewer's sigmoid recovers the
true alpha. Idempotent: a PLY already in logit space (any value outside [0,1]) is skipped.

Usage:
    python tools/fix_opacity.py scenes/pet1 [scenes/room2 ...]   # fix a scene dir (re-prunes mobile)
    python tools/fix_opacity.py path/to/file.ply                 # fix a single .ply in place
"""
import sys
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement


def _is_linear(opacity: np.ndarray) -> bool:
    """Linear-probability opacity lives in [0,1]; logit opacity has values outside it."""
    return float(opacity.min()) >= 0.0 and float(opacity.max()) <= 1.0


def fix_ply(ply_path: Path) -> bool:
    """Logit-transform opacity in place (with a .bak backup). Returns True if changed."""
    ply = PlyData.read(str(ply_path))
    vertex = ply["vertex"]
    op = np.asarray(vertex["opacity"], dtype=np.float64)
    if not _is_linear(op):
        print(f"[skip] {ply_path} already logit (min={op.min():.3f} max={op.max():.3f})")
        return False
    op_c = np.clip(op, 1e-6, 1.0 - 1e-6)
    logit = np.log(op_c / (1.0 - op_c)).astype(np.float32)
    backup = ply_path.with_suffix(ply_path.suffix + ".bak")
    if not backup.exists():
        ply_path.rename(backup)
        ply = PlyData.read(str(backup))
        vertex = ply["vertex"]
    vertex.data["opacity"] = logit
    el = PlyElement.describe(vertex.data, "vertex")
    PlyData([el], text=False).write(str(ply_path))
    print(f"[ok]   {ply_path}: linear[{op.min():.3f},{op.max():.3f}] -> "
          f"logit[{logit.min():.2f},{logit.max():.2f}]  (backup {backup.name})")
    return True


def fix_scene(scene_dir: Path) -> None:
    """Fix the full scene.ply, then regenerate scene_mobile.ply via the prune step."""
    full = scene_dir / "scene.ply"
    if not full.exists():
        # Some scenes serve scene_mobile.ply directly with no separate full ply.
        for cand in scene_dir.glob("*.ply"):
            fix_ply(cand)
        return
    changed = fix_ply(full)
    mobile = scene_dir / "scene_mobile.ply"
    if mobile.exists() and changed:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from modules.reconstruct.optimize_ply import prune_ply
        kept, total = prune_ply(full, mobile, max_gaussians=1_100_000, min_alpha=0.01)
        print(f"[ok]   re-pruned {total} -> {kept} gaussians (scene_mobile.ply, min_alpha=0.01)")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            fix_scene(p)
        elif p.suffix == ".ply":
            fix_ply(p)
        else:
            print(f"[warn] skipping {p} (not a dir or .ply)")


if __name__ == "__main__":
    main()
