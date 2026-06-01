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
# NOTE: on a 12 GB GPU keep the frame count low (~8) — the voxelization step OOMs with
# more views. More views (better quality) needs a larger/cloud GPU.
set -euo pipefail
FRAMES="$1"; RESULT="$2"; STEPS="${3:-3000}"
AS="${ANYSPLAT_ENV:-/home/liylo/anaconda3/envs/anysplat}"
cd "$(dirname "$0")/../external_AnySplat"
env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True "$AS/bin/python" \
  src/post_opt/simple_trainer.py default \
  --data-dir "$FRAMES" --result-dir "$RESULT" \
  --max-steps "$STEPS" --eval-steps 1 "$STEPS" --save-ply --ply-steps "$STEPS" \
  --disable-video --sh-degree 1
echo "Refined PLY: $RESULT/ply/  ·  metrics: $RESULT/stats/val_step*.json"
