# Reconstruction baseline — frozen reference (2026-06-04)

All quality experiments are measured against this. Do not change these defaults without
recording a new experiment row in `experiments/RESULTS.md`.

## Engine
- **AnySplat** (`lhjiang/anysplat`, MIT) — feed-forward, pure inference, **no per-scene optimization**.
- GPU: RTX 4070 Ti (12 GB). `ATTN_BACKEND=xformers`, `SPCONV_ALGO=native`, `empty_cache()` after inference.

## Input pipeline (env knobs in `modules/reconstruct/cli.py`)
| Knob | Default | Notes |
|---|---|---|
| `MAX_VIEWS` | 20 | 16 confirmed safe, 20 = edge, 24 OOMs |
| `MIN_VIEWS` | 16 | |
| `CAPTURE_RATE` | 1.5 views/sec | blur-aware: sharpest frame per time window |
| `CAPTURE_LONG_SIDE` | 0 (native) | model downsamples; pre-shrinking caused upsampling blur |
| `MAX_GAUSSIANS` | 1,100,000 | mobile prune → `scene_mobile.ply` (viewer loads this) |

## Known model behavior
- `process_image` **resizes short side → 448 and CENTER-CROPS to 448×448**. Portrait phone
  frames (1080×1920) therefore lose ~44% of the long dimension (top/bottom cropped). Square
  FOV only.
- Output opacity is linear [0,1]; we store **logit** so the viewer's sigmoid recovers true alpha.
- `up` recovered from predicted camera extrinsics (fallback: RANSAC floor plane).
- Viewer renders at `sphericalHarmonicsDegree: 0` (no view-dependent color).

## Baseline scenes (from `videos/*.MOV`, portrait, 1920×1080, rotation -90)
| Scene | Video | Dur | Frames | Views used | Gaussians (full→mobile) |
|---|---|---|---|---|---|
| room1 (bedroom) | room1.MOV | 44 s | 1311 | 20 | ~2.3M → 1.1M |
| pet1 (object) | pet1.MOV | 12 s | 373 | 19 | ~2.3M → 1.1M |

## User-reported quality problems (the targets)
1. **room1: low surface density** — sparse/holey surfaces.
2. **pet1: noisy floater background** — stringy spray splats around the object.

## Quality metric (agreed)
- **Held-out-view PSNR/SSIM/LPIPS**: hold out N frames, render from their predicted pose,
  compare to the real image. Same protocol as the AnySplat paper. (Harness: TBD.)

## Decisions for this effort
- Budget: generous (multi-run sweeps + post-opt OK).
- Post-optimization: **YES** — add a gsplat photometric refinement stage after feed-forward.
- Primary target: **room first** (room1), then transfer learnings to the object.
