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
    d = scene_dir(scenes_root, scene_id)
    frames = extract_frames(video, str(d / "frames"), max_frames=16, long_side=448)
    print(f"extracted {len(frames)} frames; engine={engine}")
    recon = make_reconstructor(engine)
    scene = recon.reconstruct(frames, scene_id, d / "scene.ply")
    save_scene(scenes_root, scene)
    print(f"wrote {d / 'scene.ply'} with {scene.source_meta['n_gaussians']} gaussians")


if __name__ == "__main__":
    main()
