"""AnySplat reconstruction adapter — pins the real AnySplat inference API.

Real flow (from the AnySplat repo, cloned locally and added to sys.path at load time):
    model = AnySplat.from_pretrained("lhjiang/anysplat").to(device).eval()
    imgs  = [process_image(p) for p in paths]
    images = torch.stack(imgs, 0).unsqueeze(0)          # [1, K, 3, 448, 448]
    gaussians, pred_context_pose = model.inference((images + 1) * 0.5)
    export_ply(means[0], scales[0], rotations[0], harmonics[0], opacities[0], path)

All heavy imports (torch, AnySplat `src.*`) are LAZY so this module imports — and the
mocked smoke tests run — without torch/AnySplat installed. Point at the cloned repo with
the ANYSPLAT_ROOT env var (defaults to <repo>/external_AnySplat).
"""
import os
import sys
from pathlib import Path

import numpy as np

from modules.scene_store.contracts import SplatScene

DEFAULT_ANYSPLAT_ROOT = os.environ.get(
    "ANYSPLAT_ROOT", str(Path(__file__).resolve().parents[2] / "external_AnySplat")
)


def up_from_extrinsics(c2w: np.ndarray) -> list[float] | None:
    """World gravity-up from cam2world extrinsics `[V,4,4]` in OpenCV convention.

    AnySplat predicts cameras in the OpenCV frame where each camera's local +Y points DOWN.
    For an upright-held phone, world-up ≈ the negated mean of the cameras' world-space Y axes
    (Nerfstudio's `auto_orient_and_center_poses(method="up")`). Returns a unit `[x,y,z]` in the
    same (CV) frame as the exported Gaussians, or None if degenerate."""
    c2w = np.asarray(c2w, dtype=np.float64)
    if c2w.ndim != 3 or c2w.shape[1:] != (4, 4) or c2w.shape[0] == 0:
        return None
    up = -c2w[:, :3, 1].mean(axis=0)  # camera +Y = down  ->  world-up ≈ -mean(cam_y_world)
    n = float(np.linalg.norm(up))
    if n < 1e-8:
        return None
    return (up / n).tolist()


def up_from_plane(xyz: np.ndarray, up_prior, bbox, iters: int = 1000,
                  seed: int = 0) -> list[float] | None:
    """RANSAC dominant-plane (floor/table) normal as up; sign disambiguated by `up_prior`.

    Fallback for scenes with no saved poses. `eps` scales to ~1.5% of the bbox diagonal
    (AnySplat is up-to-scale). Returns a unit `[x,y,z]` or None."""
    xyz = np.asarray(xyz, dtype=np.float64)
    if xyz.shape[0] < 100:
        return None
    diag = float(np.linalg.norm(np.asarray(bbox[1]) - np.asarray(bbox[0])))
    eps = max(diag * 0.015, 1e-6)
    rng = np.random.default_rng(seed)
    pts = xyz[rng.choice(xyz.shape[0], min(xyz.shape[0], 20000), replace=False)]
    best_n, best_inl = None, -1
    for _ in range(iters):
        s = pts[rng.choice(pts.shape[0], 3, replace=False)]
        nrm = np.cross(s[1] - s[0], s[2] - s[0])
        ln = np.linalg.norm(nrm)
        if ln < 1e-9:
            continue
        nrm = nrm / ln
        inl = int((np.abs((pts - s[0]) @ nrm) < eps).sum())
        if inl > best_inl:
            best_inl, best_n = inl, nrm
    if best_n is None:
        return None
    if up_prior is not None and float(np.dot(best_n, np.asarray(up_prior, float))) < 0:
        best_n = -best_n
    return best_n.tolist()


class AnySplatReconstructor:
    def __init__(self, device: str = "cuda", long_side: int = 448,
                 max_views: int = 16, repo_root: str | None = None):
        self.device = device
        self.long_side = long_side
        self.max_views = max_views
        self.repo_root = repo_root or DEFAULT_ANYSPLAT_ROOT
        self._model = None

    def _ensure_repo_on_path(self) -> None:
        if self.repo_root not in sys.path:
            sys.path.insert(0, self.repo_root)

    def _load(self):
        if self._model is None:
            os.environ.setdefault("ATTN_BACKEND", "xformers")
            os.environ.setdefault("SPCONV_ALGO", "native")
            self._ensure_repo_on_path()
            import torch  # noqa: F401 (lazy)
            from src.model.model.anysplat import AnySplat

            model = AnySplat.from_pretrained("lhjiang/anysplat").to(self.device)
            model.eval()
            for p in model.parameters():
                p.requires_grad = False
            self._model = model
        return self._model

    def _run_anysplat(self, image_paths: list[Path]):
        """Return (gaussians, pred_context_pose) from AnySplat for the given images."""
        model = self._load()
        import torch
        # License-clean preprocessor (replaces AnySplat's CC-BY-NC src.utils.image.process_image).
        # CROP_LONG_CAP keeps more of the long side than the original 448² square crop: 616 recovers
        # ~38% vertical FOV on portrait phone frames -> +1.32x gaussian density on rooms and a clean
        # PSNR/SSIM/LPIPS win on objects (experiments/RESULTS.md rank-2). 784 OOMs at 16 views; 448
        # reproduces the old square behavior. Default 616 (validated safe on the 4070 Ti).
        from modules.reconstruct.preprocess import process_image
        long_cap = int(os.environ.get("CROP_LONG_CAP", "616"))

        imgs = [process_image(str(p), long_cap=long_cap) for p in image_paths]
        images = torch.stack(imgs, dim=0).unsqueeze(0).to(self.device)  # [1,K,3,448,W]
        with torch.no_grad():
            gaussians, pred_context_pose = model.inference((images + 1) * 0.5)
        torch.cuda.empty_cache()
        return gaussians, pred_context_pose

    def _export_ply(self, gaussians, out_ply: Path) -> None:
        """Write a standard 3DGS .ply (INRIA format) for the web splat renderer."""
        self._ensure_repo_on_path()
        import torch
        from src.model.ply_export import export_ply

        # AnySplat outputs opacity as a LINEAR probability in [0,1], and export_ply writes
        # it verbatim. But the web viewer (and the standard 3DGS .ply convention) applies a
        # sigmoid on load — so a linear value renders as sigmoid([0,1]) = 0.50..0.73, i.e.
        # nothing is ever fully opaque or invisible (see-through surfaces + ghost haze).
        # Store the LOGIT so the viewer's sigmoid recovers the true alpha.
        op = gaussians.opacities[0].clamp(1e-6, 1.0 - 1e-6)
        op_logit = torch.log(op / (1.0 - op))
        export_ply(
            gaussians.means[0], gaussians.scales[0], gaussians.rotations[0],
            gaussians.harmonics[0], op_logit, Path(out_ply),
        )

    def _gaussian_xyz(self, gaussians) -> np.ndarray:
        """(N, 3) gaussian centers for the first (only) batch element."""
        return np.asarray(gaussians.means[0].detach().cpu().numpy())

    def _estimate_up(self, pose, xyz: np.ndarray, bbox) -> tuple[list[float], str]:
        """Recover the scene's gravity-up (in the .ply's CV frame). Primary: average of the
        predicted cameras' up axes. Fallback: RANSAC floor-plane normal. Default: +Y."""
        ext = None
        if pose and "extrinsic" in pose:
            e = pose["extrinsic"]
            e = e.detach().cpu().numpy() if hasattr(e, "detach") else np.asarray(e)
            ext = e[0] if e.ndim == 4 else e
        up_cam = up_from_extrinsics(ext) if ext is not None else None
        if up_cam is not None:
            return up_cam, "camera"
        up_floor = up_from_plane(xyz, None, bbox)
        if up_floor is not None:
            return up_floor, "floor"
        return [0.0, 1.0, 0.0], "default"

    def reconstruct(self, image_paths: list[Path], scene_id: str, out_ply: Path) -> SplatScene:
        out_ply = Path(out_ply)
        capped = list(image_paths)[: self.max_views]
        gaussians, pose = self._run_anysplat(capped)
        self._export_ply(gaussians, out_ply)
        xyz = self._gaussian_xyz(gaussians)
        bbox = [xyz.min(0).tolist(), xyz.max(0).tolist()]
        up, up_source = self._estimate_up(pose, xyz, bbox)
        return SplatScene(
            id=scene_id, ply=out_ply.name, bbox=bbox,
            up=up, scale_hint=1.0,
            source_meta={"model": "anysplat", "n_views": len(capped),
                         "n_gaussians": int(xyz.shape[0]), "up_source": up_source},
        )
