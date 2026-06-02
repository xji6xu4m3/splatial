import os
import sys
from pathlib import Path
from modules.capture.frames import extract_frames
from modules.scene_store.store import save_scene, scene_dir
from modules.reconstruct.factory import make_reconstructor


def main():
    if len(sys.argv) != 4:
        print("usage: python -m modules.reconstruct.cli <video> <scenes_root> <scene_id>")
        sys.exit(2)
    video, scenes_root, scene_id = sys.argv[1], sys.argv[2], sys.argv[3]
    engine = os.environ.get("RECON_ENGINE", "anysplat")  # one-line swap: anysplat | vggt
    # Guard against path traversal: scene_id must be a plain name with no path separators
    if Path(scene_id).parts != (scene_id,):
        print(f"error: scene_id must not contain path separators or '..': {scene_id!r}")
        sys.exit(2)
    max_views = int(os.environ.get("MAX_VIEWS", "20"))  # 12GB: 16 confirmed, 20 is at the edge (24 OOMs)
    # AnySplat's process_image always resizes the SHORT side to 448 and center-crops to 448x448.
    # Feeding NATIVE frames (long_side=0) lets it DOWNsample sharp pixels; pre-shrinking to 448
    # made it UPSAMPLE a blurry 252-tall image (Bug 4). 0 = native (recommended).
    cap_long_side = int(os.environ.get("CAPTURE_LONG_SIDE", "0"))
    # Blur-aware fixed-rate sampling: ~CAPTURE_RATE views/sec, clamped to [MIN_VIEWS, max_views],
    # keeping the sharpest frame per time window. Coverage scales with clip length (VRAM-bounded).
    rate = float(os.environ.get("CAPTURE_RATE", "1.5"))
    min_views = int(os.environ.get("MIN_VIEWS", "16"))
    d = scene_dir(scenes_root, scene_id)
    frames = extract_frames(video, str(d / "frames"), max_frames=max_views,
                            long_side=cap_long_side, rate=rate, min_frames=min_views)
    print(f"extracted {len(frames)} frames; engine={engine}; views=[{min_views},{max_views}]@{rate}/s; "
          f"long_side={cap_long_side or 'native'}")
    recon = make_reconstructor(engine)
    recon.max_views = max_views  # let the reconstructor consume all sampled views
    scene = recon.reconstruct(frames, scene_id, d / "scene.ply")
    print(f"wrote {d / 'scene.ply'} with {scene.source_meta['n_gaussians']} gaussians")

    # Mobile-friendly prune: phones can't load multi-million-splat PLYs. Emit a capped
    # scene_mobile.ply and point the scene at it (full PLY kept as source_meta.full_ply).
    cap = int(os.environ.get("MAX_GAUSSIANS", "1100000"))
    if scene.source_meta["n_gaussians"] > cap:
        from modules.reconstruct.optimize_ply import prune_ply
        kept, total = prune_ply(d / "scene.ply", d / "scene_mobile.ply", max_gaussians=cap)
        scene.source_meta["full_ply"] = "scene.ply"
        scene.source_meta["n_gaussians"] = kept
        scene.ply = "scene_mobile.ply"
        print(f"pruned {total} -> {kept} gaussians (scene_mobile.ply)")
    save_scene(scenes_root, scene)


if __name__ == "__main__":
    main()
