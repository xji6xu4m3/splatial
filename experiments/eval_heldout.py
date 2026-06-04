"""Held-out-view PSNR/SSIM/LPIPS for an AnySplat reconstruction — the experiment metric spine.

Faithful port of external_AnySplat/src/eval_nvs.py, pointed at our scene frame folders.

Protocol (true novel-view, single consistent coordinate frame):
  1. Split the selected frames into context (kept) and held-out target (every Nth) views.
  2. Reconstruct gaussians from CONTEXT ONLY  -> genuinely held-out targets.
  3. Recover target poses in the gaussians' frame: run the pose head on context+target
     jointly, then rescale target translations by the context translation ratio
     (the shared context views bridge the two passes' arbitrary scales).
  4. Render the target poses with AnySplat's own decoder; score vs the real held-out images.

Runs in the `anysplat` conda env (needs torch, the AnySplat repo, gsplat, lpips, skimage).

Usage:
    conda run -n anysplat python experiments/eval_heldout.py --scene room1 --scene pet1
    # or point at an arbitrary frames dir:
    conda run -n anysplat python experiments/eval_heldout.py --frames scenes/room1/frames
"""
import argparse
import os
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
ANYSPLAT_ROOT = os.environ.get("ANYSPLAT_ROOT", str(ROOT / "external_AnySplat"))
if ANYSPLAT_ROOT not in sys.path:
    sys.path.insert(0, ANYSPLAT_ROOT)

os.environ.setdefault("ATTN_BACKEND", "xformers")
os.environ.setdefault("SPCONV_ALGO", "native")

IMG_EXT = (".png", ".jpg", ".jpeg")


def list_frames(frames_dir: Path) -> list[str]:
    return sorted(str(p) for p in frames_dir.iterdir() if p.suffix.lower() in IMG_EXT)


def load_model(device):
    from src.model.model.anysplat import AnySplat
    model = AnySplat.from_pretrained("lhjiang/anysplat").to(device).eval()
    for p in model.parameters():
        p.requires_grad = False
    return model


def _get_preprocessor():
    """CROP_LONG_CAP env: 0/unset -> AnySplat's square-448 process_image (baseline).
    >0 -> our license-clean preprocessor keeping the long side up to that cap (mult of 14)."""
    cap = int(os.environ.get("CROP_LONG_CAP", "0"))
    if cap > 0:
        from modules.reconstruct.preprocess import process_image as pi
        return (lambda p: pi(p, long_cap=cap)), f"tall{cap}"
    from src.utils.image import process_image as pi
    return pi, "square448"


def eval_scene(model, device, frames_dir: Path, holdout: int, preprocess):
    from src.model.encoder.vggt.utils.pose_enc import pose_encoding_to_extri_intri
    from src.evaluation.metrics import compute_psnr, compute_ssim, compute_lpips

    names = list_frames(frames_dir)
    n = len(names)
    if n < holdout + 2:
        raise SystemExit(f"{frames_dir}: only {n} frames, need >= {holdout + 2}")
    images = [preprocess(p) for p in names]  # each [3,H,W] in [-1,1]

    ctx_idx = [i for i in range(n) if i % holdout != 0]
    tgt_idx = [i for i in range(n) if i % holdout == 0]

    ctx = (torch.stack([images[i] for i in ctx_idx], 0).unsqueeze(0).to(device) + 1) * 0.5
    tgt = (torch.stack([images[i] for i in tgt_idx], 0).unsqueeze(0).to(device) + 1) * 0.5
    b, v, _, h, w = tgt.shape

    # 1+2: reconstruct gaussians from CONTEXT only
    enc = model.encoder(ctx, global_step=0, visualization_dump={})
    gaussians, pred_context_pose = enc.gaussians, enc.pred_context_pose
    n_ctx = ctx.shape[1]

    # 3: recover target poses in a shared frame via a joint pose pass + scale alignment
    joint = torch.cat((ctx, tgt), dim=1).to(torch.bfloat16)
    with torch.no_grad(), torch.cuda.amp.autocast(enabled=False, dtype=torch.bfloat16):
        tokens, _ = model.encoder.aggregator(
            joint, intermediate_layer_idx=model.encoder.cfg.intermediate_layer_idx)
    with torch.cuda.amp.autocast(enabled=False):
        tokens = [t.float() for t in tokens]
        pose_enc = model.encoder.camera_head(tokens)[-1]
        all_ext, all_int = pose_encoding_to_extri_intri(pose_enc, joint.shape[-2:])
    pad = torch.tensor([0, 0, 0, 1], device=all_ext.device, dtype=all_ext.dtype)
    pad = pad.view(1, 1, 1, 4).repeat(b, joint.shape[1], 1, 1)
    all_ext = torch.cat([all_ext, pad], dim=2).inverse()
    all_int[:, :, 0] = all_int[:, :, 0] / w
    all_int[:, :, 1] = all_int[:, :, 1] / h
    ctx_ext, tgt_ext = all_ext[:, :n_ctx], all_ext[:, n_ctx:]
    _, tgt_int = all_int[:, :n_ctx], all_int[:, n_ctx:]
    scale = pred_context_pose["extrinsic"][:, :, :3, 3].mean() / ctx_ext[:, :, :3, 3].mean()
    tgt_ext = tgt_ext.clone()
    tgt_ext[..., :3, 3] = tgt_ext[..., :3, 3] * scale

    # 4: render target poses + score
    out = model.decoder.forward(
        gaussians, tgt_ext, tgt_int.float(),
        torch.ones(1, v, device=device) * 0.01,
        torch.ones(1, v, device=device) * 100.0,
        (h, w),
    )
    pred = out.color[0].clamp(0, 1)
    gt = tgt[0].clamp(0, 1)
    psnr = compute_psnr(gt, pred).mean().item()
    ssim = compute_ssim(gt, pred).mean().item()
    lpips = compute_lpips(gt, pred).mean().item()
    torch.cuda.empty_cache()
    return {"frames": n, "ctx": n_ctx, "tgt": int(v),
            "psnr": psnr, "ssim": ssim, "lpips": lpips}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", action="append", default=[], help="scene id under scenes/")
    ap.add_argument("--frames", action="append", default=[], help="explicit frames dir")
    ap.add_argument("--holdout", type=int, default=5, help="hold out every Nth frame")
    ap.add_argument("--tag", default="baseline", help="label for the results log line")
    args = ap.parse_args()

    dirs = [(s, ROOT / "scenes" / s / "frames") for s in args.scene]
    dirs += [(Path(f).parent.name, Path(f)) for f in args.frames]
    if not dirs:
        raise SystemExit("pass --scene <id> and/or --frames <dir>")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = load_model(device)
    preprocess, prep_tag = _get_preprocessor()
    print(f"# tag={args.tag} holdout=every-{args.holdout}th preprocess={prep_tag}")
    print(f"{'scene':<12} {'frames':>6} {'ctx':>4} {'tgt':>4} {'PSNR':>7} {'SSIM':>6} {'LPIPS':>6}")
    for name, d in dirs:
        if not d.is_dir():
            print(f"{name:<12} (no frames dir: {d})")
            continue
        r = eval_scene(model, device, d, args.holdout, preprocess)
        print(f"{name:<12} {r['frames']:>6} {r['ctx']:>4} {r['tgt']:>4} "
              f"{r['psnr']:>7.2f} {r['ssim']:>6.3f} {r['lpips']:>6.3f}")


if __name__ == "__main__":
    main()
