"""AnySplat reconstruction adapter.

Fill the AnySplat calls in `_run_anysplat` / `_export_ply` from the repo example
(pinned in Task 3 Step 1). Everything else here is our stable contract.

AnySplat repo: https://github.com/InternRobotics/AnySplat
  - Load:   from anysplat import AnySplat; model = AnySplat.from_pretrained("lhjiang/anysplat").to(device)
  - Run:    gaussians, cameras = model.run(image_paths)
  - Export: gaussians.save_ply(str(out_ply))
  - XYZ:    gaussians.means.detach().cpu().numpy()  -> (N, 3) float32
"""
import os
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
            # Apply 12 GB flags before importing torch-heavy modules
            os.environ.setdefault("ATTN_BACKEND", "xformers")
            os.environ.setdefault("SPCONV_ALGO", "native")
            # Lazy import: torch and anysplat are NOT imported at module level
            from anysplat import AnySplat  # exact import per repo example
            self._model = AnySplat.from_pretrained("lhjiang/anysplat").to(self.device)
        return self._model

    def _run_anysplat(self, image_paths: list[Path]):
        """Return (gaussians, cameras) from AnySplat for the given images."""
        model = self._load()
        # exact call per repo example; images capped to self.max_views, resized to long_side
        result = model.run(image_paths)  # placeholder name -> replace with the real entrypoint
        import torch
        torch.cuda.empty_cache()
        return result

    def _export_ply(self, gaussians, out_ply: Path) -> None:
        """Write standard 3DGS .ply (INRIA format) for the web splat renderer."""
        # use the repo's export util
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
        # adapt to the repo's gaussian container
        return np.asarray(gaussians.means.detach().cpu().numpy())
