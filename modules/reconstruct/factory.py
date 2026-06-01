"""Reconstructor factory. RECON_ENGINE picks the engine; both impls share the
identical reconstruct(image_paths, scene_id, out_ply) -> SplatScene contract."""
from modules.reconstruct.anysplat_provider import AnySplatReconstructor
from modules.reconstruct.vggt_provider import VGGTReconstructor


def make_reconstructor(engine: str = "anysplat"):
    engine = (engine or "anysplat").lower()
    if engine == "anysplat":
        return AnySplatReconstructor()
    if engine == "vggt":
        return VGGTReconstructor()
    raise ValueError(f"unknown RECON_ENGINE: {engine!r} (expected 'anysplat' | 'vggt')")
