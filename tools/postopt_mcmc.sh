#!/usr/bin/env bash
# Offline QUALITY step (MCMC variant): refine a feed-forward AnySplat scene with per-scene
# gsplat optimization using the MCMC strategy instead of DefaultStrategy.
#
# Usage:   tools/postopt_mcmc.sh <frames_dir> <result_dir> [max_steps]
# Example: tools/postopt_mcmc.sh scenes/hires/frames scenes/hires/postopt_mcmc 3000
#
# WHY MCMC (vs the `default` DefaultStrategy in postopt.sh):
# DefaultStrategy prunes low-opacity splats and only densifies high-gradient (textured)
# regions, so smooth low-texture surfaces (plain walls, bed, floor) get thinned into GAPS
# while textured areas oversharpen into needle/speckle artifacts. MCMC ("3DGS as Markov
# Chain Monte Carlo") instead keeps a FIXED budget (--strategy.cap-max): a splat that dies
# is RELOCATED to a high-error spot rather than pruned, so coverage stays uniform — no holes
# on smooth surfaces. opacity_reg kills the translucent haze; scale_reg caps the needles.
# Net intent: keep post-opt's sharpness but eliminate the gaps + needles + rainbow speckle.
#
# CAP_MAX (env, default 8M): the fixed gaussian budget. Init from the feed-forward encoder is
# ~5-6M at 42 views; set CAP_MAX above that so MCMC can ADD splats to fill under-covered areas.
# VRAM scales with cap-max: 8M needs an A100 (40GB) comfortably; on L4 (24GB) drop to ~4-5M.
#
# SH degree MUST be 0 (web viewer reads only f_dc) — see postopt.sh for the full rationale.
set -euo pipefail
FRAMES="$1"; RESULT="$2"; STEPS="${3:-3000}"
AS="${ANYSPLAT_ENV:-/home/liylo/anaconda3/envs/anysplat}"
CAP_MAX="${CAP_MAX:-8000000}"
cd "$(dirname "$0")/../external_AnySplat"
env PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True "$AS/bin/python" \
  src/post_opt/simple_trainer.py mcmc \
  --data-dir "$FRAMES" --result-dir "$RESULT" \
  --max-steps "$STEPS" --eval-steps 1 "$STEPS" --save-ply --ply-steps "$STEPS" \
  --disable-video --sh-degree 0 \
  --opacity-reg 0.01 --scale-reg 0.01 \
  --strategy.cap-max "$CAP_MAX"
echo "Refined PLY (MCMC, cap=$CAP_MAX): $RESULT/ply/  ·  metrics: $RESULT/stats/val_step*.json"
