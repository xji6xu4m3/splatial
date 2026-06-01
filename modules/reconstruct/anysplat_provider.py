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
        from src.utils.image import process_image

        imgs = [process_image(str(p)) for p in image_paths]
        images = torch.stack(imgs, dim=0).unsqueeze(0).to(self.device)  # [1,K,3,448,448]
        with torch.no_grad():
            gaussians, pred_context_pose = model.inference((images + 1) * 0.5)
        torch.cuda.empty_cache()
        return gaussians, pred_context_pose

    def _export_ply(self, gaussians, out_ply: Path) -> None:
        """Write a standard 3DGS .ply (INRIA format) for the web splat renderer."""
        self._ensure_repo_on_path()
        from src.model.ply_export import export_ply

        export_ply(
            gaussians.means[0], gaussians.scales[0], gaussians.rotations[0],
            gaussians.harmonics[0], gaussians.opacities[0], Path(out_ply),
        )

    def _gaussian_xyz(self, gaussians) -> np.ndarray:
        """(N, 3) gaussian centers for the first (only) batch element."""
        return np.asarray(gaussians.means[0].detach().cpu().numpy())

    def reconstruct(self, image_paths: list[Path], scene_id: str, out_ply: Path) -> SplatScene:
        out_ply = Path(out_ply)
        capped = list(image_paths)[: self.max_views]
        gaussians, _pose = self._run_anysplat(capped)
        self._export_ply(gaussians, out_ply)
        xyz = self._gaussian_xyz(gaussians)
        bbox = [xyz.min(0).tolist(), xyz.max(0).tolist()]
        return SplatScene(
            id=scene_id, ply=out_ply.name, bbox=bbox,
            up=[0.0, 1.0, 0.0], scale_hint=1.0,
            source_meta={"model": "anysplat", "n_views": len(capped),
                         "n_gaussians": int(xyz.shape[0])},
        )
