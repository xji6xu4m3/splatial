"""VGGT + gsplat reconstruction adapter (fallback for AnySplat).

Fill the VGGT and gsplat calls (marked TODO-PIN) from the repo examples:
- VGGT-1B-Commercial: load + predict poses/depth/pointmaps from image paths.
  Repo: https://github.com/facebookresearch/vggt
  Load:    from vggt import VGGT; model = VGGT.from_pretrained("facebook/VGGT-1B-Commercial").to(device)
  Predict: output = model.predict(image_paths)  -> {poses, depth, pointmaps}
- gsplat (nerfstudio-project/gsplat): init a 3DGS from the pointmaps, optimize
  ~1-3k steps, export a standard INRIA 3DGS .ply.
  Repo: https://github.com/nerfstudio-project/gsplat
  Init+Opt: gaussians = gsplat_init_and_optimize(vggt_out, steps=opt_steps)
  Export:   gaussians.save_ply(str(out_ply))
Everything else here is our stable contract, identical to AnySplatReconstructor.
"""
import os
from pathlib import Path
import numpy as np
from modules.scene_store.contracts import SplatScene


class VGGTReconstructor:
    def __init__(self, device: str = "cuda", long_side: int = 448,
                 max_views: int = 16, opt_steps: int = 2000):
        self.device = device
        self.long_side = long_side
        self.max_views = max_views
        self.opt_steps = opt_steps
        self._model = None

    def _load(self):
        if self._model is None:
            # Apply 12 GB flags before importing torch-heavy modules
            os.environ.setdefault("ATTN_BACKEND", "xformers")
            os.environ.setdefault("SPCONV_ALGO", "native")
            # TODO-PIN: exact import/load per VGGT-1B-Commercial repo example
            from vggt import VGGT  # exact import per repo example
            self._model = VGGT.from_pretrained("facebook/VGGT-1B-Commercial").to(self.device)
        return self._model

    def _run_vggt(self, image_paths: list[Path]):
        """Return poses + depth + pointmaps from VGGT for the given images."""
        model = self._load()
        # TODO-PIN: exact call per repo example -> {poses, depth, pointmaps}
        return model.predict(image_paths)

    def _optimize_gsplat(self, vggt_out, out_ply: Path):
        """Init a 3DGS from VGGT pointmaps, optimize with gsplat, export .ply.
        Returns the gaussian container (means accessible like AnySplat's)."""
        # TODO-PIN: nerfstudio-project/gsplat init from pointmaps + ~self.opt_steps
        #           rasterization-loss optimization, then export INRIA 3DGS .ply.
        raise NotImplementedError(
            "TODO-PIN: fill gsplat_init_and_optimize from nerfstudio-project/gsplat — "
            "init a 3DGS from vggt_out pointmaps, optimize ~self.opt_steps steps, "
            "call gaussians.save_ply(str(out_ply)), and return gaussians."
        )
        return gaussians

    def reconstruct(self, image_paths: list[Path], scene_id: str, out_ply: Path) -> SplatScene:
        capped = image_paths[: self.max_views]
        vggt_out = self._run_vggt(capped)
        gaussians = self._optimize_gsplat(vggt_out, out_ply)
        xyz = self._gaussian_xyz(gaussians)          # (N,3) numpy
        bbox = [xyz.min(0).tolist(), xyz.max(0).tolist()]
        return SplatScene(
            id=scene_id, ply=out_ply.name, bbox=bbox,
            up=[0.0, 1.0, 0.0], scale_hint=1.0,
            source_meta={"model": "vggt+gsplat", "n_views": len(capped),
                         "opt_steps": self.opt_steps, "n_gaussians": int(xyz.shape[0])},
        )

    @staticmethod
    def _gaussian_xyz(gaussians) -> np.ndarray:
        # adapt to gsplat's gaussian container (e.g. gaussians.means.cpu().numpy())
        return np.asarray(gaussians.means.detach().cpu().numpy())
