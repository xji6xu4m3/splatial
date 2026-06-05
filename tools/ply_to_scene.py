"""Wrap a standard INRIA 3DGS .ply (e.g. YoNoSplat's export) into a viewer scene folder:
scenes/<id>/{scene.ply, scene.json}. Computes bbox from the gaussian centers; `up` defaults to
+Y (YoNoSplat's pose-free frame is arbitrary — adjust in the viewer's Level tool if the floor tilts).

Usage:  python tools/ply_to_scene.py <input.ply> <scene_id> [--up 0 1 0]
"""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from plyfile import PlyData

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("ply")
    ap.add_argument("scene_id")
    ap.add_argument("--up", type=float, nargs=3, default=[0.0, 1.0, 0.0])
    args = ap.parse_args()

    v = PlyData.read(args.ply)["vertex"].data
    xyz = np.stack([v["x"], v["y"], v["z"]], 1).astype(float)
    out = ROOT / "scenes" / args.scene_id
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.ply, out / "scene.ply")
    json.dump({
        "id": args.scene_id, "ply": "scene.ply",
        "bbox": [xyz.min(0).tolist(), xyz.max(0).tolist()],
        "up": args.up, "scale_hint": 1.0,
        "source_meta": {"model": "yonosplat", "n_gaussians": int(len(xyz))},
    }, open(out / "scene.json", "w"), indent=2)
    print(f"{args.scene_id}: {len(xyz)} gaussians -> {out} (ply=scene.ply)")


if __name__ == "__main__":
    main()
