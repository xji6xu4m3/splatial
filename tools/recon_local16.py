"""One-off: reconstruct the SAME hires room from 16 evenly-spaced frames on the
local 4070 Ti, to A/B against the 48-view A100 `hires`/`hires_full`. Isolates
VIEW DENSITY (same capture, full coverage, fewer views) — the exact variable the
cloud GPU unlocked. Run with the anysplat conda env python."""
import sys
from pathlib import Path

from modules.reconstruct.anysplat_provider import AnySplatReconstructor
from modules.scene_store.store import save_scene, scene_dir
from modules.reconstruct.optimize_ply import prune_ply

SCENES = "scenes"
SCENE_ID = "hires_local16"
SRC_FRAMES = Path("scenes/hires/frames")
N = 16

frames = sorted(SRC_FRAMES.glob("frame_*.png"))
if not frames:
    sys.exit(f"no frames in {SRC_FRAMES}")
# evenly subsample N from the full set -> same coverage, lower density
idx = [round(i * (len(frames) - 1) / (N - 1)) for i in range(N)]
picked = [frames[i] for i in sorted(set(idx))]
print(f"picked {len(picked)}/{len(frames)} frames: {[p.name for p in picked]}")

d = scene_dir(SCENES, SCENE_ID)
recon = AnySplatReconstructor(max_views=N)
scene = recon.reconstruct(picked, SCENE_ID, d / "scene.ply")
print(f"wrote {d/'scene.ply'} with {scene.source_meta['n_gaussians']} gaussians")

cap = 1_100_000
if scene.source_meta["n_gaussians"] > cap:
    kept, total = prune_ply(d / "scene.ply", d / "scene_mobile.ply",
                            max_gaussians=cap, min_alpha=0.004, mode="room")
    scene.source_meta["full_ply"] = "scene.ply"
    scene.source_meta["n_gaussians"] = kept
    scene.ply = "scene_mobile.ply"
    print(f"pruned {total} -> {kept} gaussians (scene_mobile.ply)")
save_scene(SCENES, scene)
print(f"saved scene {SCENE_ID}: ply={scene.ply}, up={scene.up}")
