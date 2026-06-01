"""Prune a 3DGS .ply to a target Gaussian count for mobile viewing.

AnySplat exports the standard degree-0 layout (x,y,z,nx,ny,nz,f_dc_0..2,opacity,
scale_0..2,rot_0..3 = 17 floats/gaussian), which the web viewer renders at SH degree 0.
The only lever for file size / GPU memory is the gaussian COUNT, so we drop the
lowest-opacity gaussians (they contribute least) down to `max_gaussians`.

`select_indices` is pure (numpy only) and unit-tested; `prune_ply` does the .ply I/O
(needs `plyfile`, available in the anysplat env).
"""
from pathlib import Path

import numpy as np


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def select_indices(alpha: np.ndarray, max_gaussians: int, min_alpha: float = 0.0,
                   seed: int = 0) -> np.ndarray:
    """Indices to KEEP for a size cap.

    Drop the truly-invisible (alpha < min_alpha), then if still over the cap, take a
    UNIFORM RANDOM subsample. Uniform sampling thins the whole scene evenly and preserves
    the background — unlike opacity-ranked pruning, which deletes low-opacity walls/sky
    and leaves white holes. Deterministic for a given seed. Returns sorted indices.
    """
    idx = np.nonzero(alpha >= min_alpha)[0]
    if idx.size > max_gaussians:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(idx, size=max_gaussians, replace=False))
    return idx


def prune_ply(in_ply: str | Path, out_ply: str | Path,
              max_gaussians: int = 1_000_000, min_alpha: float = 0.004) -> tuple[int, int]:
    """Write a pruned copy of `in_ply` to `out_ply`. Returns (kept, total)."""
    from plyfile import PlyData, PlyElement

    ply = PlyData.read(str(in_ply))
    vertex = ply["vertex"]
    total = len(vertex.data)
    alpha = _sigmoid(np.asarray(vertex["opacity"], dtype=np.float64))
    keep = select_indices(alpha, max_gaussians, min_alpha)
    el = PlyElement.describe(vertex.data[keep], "vertex")
    PlyData([el], text=False).write(str(out_ply))
    return int(keep.size), int(total)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Prune a 3DGS .ply to a target gaussian count")
    ap.add_argument("in_ply")
    ap.add_argument("out_ply")
    ap.add_argument("--max", type=int, default=1_000_000, dest="max_gaussians")
    ap.add_argument("--min-alpha", type=float, default=0.004)
    a = ap.parse_args()
    kept, total = prune_ply(a.in_ply, a.out_ply, a.max_gaussians, a.min_alpha)
    print(f"pruned {total} -> {kept} gaussians ({a.out_ply})")


if __name__ == "__main__":
    main()
