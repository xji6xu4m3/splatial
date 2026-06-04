#!/usr/bin/env bash
# Optional offline QUALITY step: refine a feed-forward AnySplat scene with per-scene
# gsplat optimization (AnySplat's post_opt) and report PSNR/SSIM/LPIPS on held-out views.
#
# Usage:   tools/postopt.sh <frames_dir> <result_dir> [max_steps]
# Example: tools/postopt.sh scenes/room2/frames8 scenes/room2/postopt 3000
#
# Prereqs (one-time): clone AnySplat to external_AnySplat/, run tools/patch_anysplat.py,
# and install post-opt deps in the anysplat env (see modules/reconstruct/README.md).
#
# VRAM: verified to fit ~17 init views at 448² in ~9.9 GB on a 12 GB card (with the
# no_grad init patch + expandable_segments). The old "~8 views OOMs" note was stale.
#
# SH degree MUST be 0: the web viewer renders at sphericalHarmonicsDegree 0 (reads only
# f_dc). Training at SH>=1 pushes color into f_rest coefficients the viewer ignores, so the
# scene renders washed-out / colour-fringed even though the trainer's PSNR (which renders the
# full SH) looks better. Keep SH0 so the optimized colour lives entirely in f_dc.
set -euo pipefail
FRAMES="$1"; RESULT="$2"; STEPS="${3:-3000}"
AS="${ANYSPLAT_ENV:-/home/liylo/anaconda3/envs/anysplat}"
cd "$(dirname "$0")/../external_AnySplat"
env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True "$AS/bin/python" \
  src/post_opt/simple_trainer.py default \
  --data-dir "$FRAMES" --result-dir "$RESULT" \
  --max-steps "$STEPS" --eval-steps 1 "$STEPS" --save-ply --ply-steps "$STEPS" \
  --disable-video --sh-degree 0
echo "Refined PLY: $RESULT/ply/  ·  metrics: $RESULT/stats/val_step*.json"
