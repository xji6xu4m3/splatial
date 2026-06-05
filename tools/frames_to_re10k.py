"""Pack a folder of unposed RGB frames into the RealEstate10K `.torch` chunk format that
YoNoSplat's (and pixelSplat's) dataset loader expects, so we can run pose-free inference on a
phone capture. See docs/analysis/2026-06-04-postopt-vs-feedforward-rootcause.md (YoNoSplat track).

Chunk format (verified from cvg/YoNoSplat src/dataset/dataset_re10k.py):
  <out_root>/test/000000.torch  = torch.save([ {key, cameras[N,18], images[list of uint8 byte tensors]} ])
    - cameras row = [fx, fy, cx, cy, _, _, w2c(3x4 flattened=12)]  (intrinsics NORMALIZED to [0,1])
    - images[i] = 1D uint8 tensor of the JPEG/PNG bytes; must DECODE to exactly original_image_shape
  <out_root>/index_eval.json    = { key: {"context":[...], "target":[...], "overlap":"large"} }

Pose-free run: the model predicts poses+intrinsics, so the stored cameras are DUMMY (identity w2c,
nominal intrinsics) — used only for the (ignored) metric path; the eval view-sampler picks frames
from index_eval.json, not from the poses. Run with original_image_shape=[SIZE,SIZE].

Usage:
  python tools/frames_to_re10k.py scenes/hires/frames datasets/hires hires --size 384 --n-context 32
"""
import argparse
import io
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageOps


def square_crop(img: Image.Image, size: int) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("out_root")
    ap.add_argument("key")
    ap.add_argument("--size", type=int, default=384, help="stored square original_image_shape (>= model input 224)")
    ap.add_argument("--n-context", type=int, default=32, help="context views (re10k ckpt trained ctx 2..32)")
    ap.add_argument("--n-target", type=int, default=4)
    args = ap.parse_args()

    frames = sorted(Path(args.frames_dir).glob("*.png")) + sorted(Path(args.frames_dir).glob("*.jpg"))
    frames = sorted(set(frames))
    n = len(frames)
    if n < 2:
        raise SystemExit(f"need >=2 frames, found {n} in {args.frames_dir}")

    images, cameras = [], []
    for i, f in enumerate(frames):
        img = square_crop(Image.open(f), args.size)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        images.append(torch.frombuffer(bytearray(buf.getvalue()), dtype=torch.uint8).clone())
        # dummy normalized intrinsics (fx,fy ~ moderate fov) + a NON-DEGENERATE w2c: spread cameras
        # along x (t_x = -0.1*i) so the loader's pose-norm scale (max pairwise camera distance) is > 0.
        # The pose-free model ignores these for geometry — they only keep the eval plumbing well-conditioned
        # (all-identity poses -> scale 0 -> jaxtyping TypeCheckError in compute_pose_norm_scale).
        w2c = np.eye(4, dtype=np.float32)
        w2c[0, 3] = -0.1 * i
        cameras.append([0.7, 0.7, 0.5, 0.5, 0.0, 0.0, *w2c[:3].reshape(-1).tolist()])

    cameras_t = torch.tensor(cameras, dtype=torch.float32)         # [N,18]
    chunk = [{"key": args.key, "cameras": cameras_t, "images": images}]

    out_root = Path(args.out_root)
    (out_root / "test").mkdir(parents=True, exist_ok=True)
    torch.save(chunk, out_root / "test" / "000000.torch")

    # evenly-spaced context across the trajectory; targets interleaved (metrics ignored)
    ctx = np.linspace(0, n - 1, min(args.n_context, n)).round().astype(int).tolist()
    ctx = sorted(set(ctx))
    remaining = [i for i in range(n) if i not in ctx]
    tgt = (remaining or ctx)[: args.n_target]
    index = {args.key: {"context": ctx, "target": tgt, "overlap": "large"}}
    (out_root / "index_eval.json").write_text(json.dumps(index, indent=1))

    print(f"wrote {out_root}/test/000000.torch  ({n} frames @ {args.size}px square)")
    print(f"  context={len(ctx)} views, target={len(tgt)}  -> {out_root}/index_eval.json")
    print(f"  run with: original_image_shape=[{args.size},{args.size}]")


if __name__ == "__main__":
    main()
