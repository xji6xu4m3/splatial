"""Convert a gsplat post-opt PLY into a viewer-ready Splatial scene.

`tools/postopt.sh` produces a refined PLY (AnySplat's gsplat trainer), but it is NOT directly
loadable by the web viewer — three conversions are needed (all discovered empirically, see
experiments/RESULTS.md "Rank-6 post-opt"):

  1. Opacity: gsplat `--save-ply` writes LINEAR opacity [0,1]; the viewer applies sigmoid and
     expects LOGIT. Without conversion every splat floats at >=0.5 alpha -> uniform fog.
  2. Needle floaters: post-opt on sparse handheld views grows pathological ultra-elongated
     gaussians (median anisotropy ~69, top 10% > 56000:1) that render as radial streaks from
     off-trajectory angles. Drop the top (100-aniso_pct)% by max/min scale ratio. (This is safe
     here precisely because post-opt needles are extreme; do NOT apply to feed-forward output,
     where flat surface disks are legitimately anisotropic — see optimize_ply.clean_floaters.)
  3. Statistical outlier removal + count cap for the mobile viewer.

Also requires `--sh-degree 0` at training time (viewer reads only f_dc); this script assumes that.

Usage (anysplat env):
    python tools/postopt_to_scene.py <refined_ply> <scene_id> [--base-scene scenes/room1/scene.json]
"""
import argparse
import json
from pathlib import Path

import numpy as np
from plyfile import PlyData, PlyElement

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("refined_ply")
    ap.add_argument("scene_id")
    ap.add_argument("--base-scene", help="scene.json to copy up-vector from (same AnySplat frame)")
    ap.add_argument("--aniso-pct", type=float, default=90.0, help="drop the most-anisotropic (100-pct)%%")
    ap.add_argument("--max-gaussians", type=int, default=1_100_000)
    args = ap.parse_args()

    data = PlyData.read(args.refined_ply)["vertex"].data.copy()
    n0 = len(data)

    # 2: drop extreme-anisotropy needles
    s = np.exp(np.stack([data["scale_0"], data["scale_1"], data["scale_2"]], 1).astype(np.float64))
    aniso = s.max(1) / np.maximum(s.min(1), 1e-12)
    data = data[aniso <= np.percentile(aniso, args.aniso_pct)]

    # 1: opacity linear -> logit
    op = np.clip(np.asarray(data["opacity"], dtype=np.float64), 1e-6, 1 - 1e-6)
    data["opacity"] = np.log(op / (1 - op)).astype(data["opacity"].dtype)

    # 3: SOR + cap
    import open3d as o3d
    xyz = np.stack([data["x"], data["y"], data["z"]], 1).astype(np.float64)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz)
    _, inl = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    data = data[np.asarray(inl, dtype=np.int64)]
    if len(data) > args.max_gaussians:
        rng = np.random.default_rng(0)
        data = data[np.sort(rng.choice(len(data), args.max_gaussians, replace=False))]

    out_dir = ROOT / "scenes" / args.scene_id
    out_dir.mkdir(parents=True, exist_ok=True)
    PlyData([PlyElement.describe(data, "vertex")], text=False).write(str(out_dir / "scene_mobile.ply"))

    xyz2 = np.stack([data["x"], data["y"], data["z"]], 1).astype(float)
    up = [0.0, 1.0, 0.0]
    if args.base_scene and Path(args.base_scene).exists():
        up = json.load(open(args.base_scene)).get("up", up)
    json.dump({
        "id": args.scene_id, "ply": "scene_mobile.ply",
        "bbox": [xyz2.min(0).tolist(), xyz2.max(0).tolist()], "up": up, "scale_hint": 1.0,
        "source_meta": {"model": "anysplat+postopt", "n_gaussians": int(len(data)),
                        "postopt": True, "sh_degree": 0},
    }, open(out_dir / "scene.json", "w"), indent=2)
    print(f"{args.scene_id}: {n0} -> {len(data)} gaussians (needle-cleaned, logit opacity) -> {out_dir}")


if __name__ == "__main__":
    main()
