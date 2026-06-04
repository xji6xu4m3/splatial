# Reconstruction quality experiments — results log

Metric: held-out-view PSNR/SSIM/LPIPS (every 5th selected frame held out, reconstruct from the
rest, render the held-out poses with AnySplat's decoder). Harness: `experiments/eval_heldout.py`.
Higher PSNR/SSIM = better; **lower LPIPS = better**. See `experiments/baseline/SETTINGS.md` for the
frozen baseline config and `experiments/research_plan.json` for the ranked plan.

| # | tag | scene | views(ctx→tgt) | PSNR↑ | SSIM↑ | LPIPS↓ | notes |
|---|-----|-------|----------------|-------|-------|--------|-------|
| 0 | baseline | room1 | 16→4 | 17.46 | 0.710 | 0.460 | AnySplat square 448² crop (CC-BY-NC), feed-forward only |
| 0 | baseline | pet1  | 15→4 | 19.12 | 0.619 | 0.478 | AnySplat square 448² crop, feed-forward only |
| 0c | clean448 (control) | room1 | 16→4 | 17.49 | 0.708 | 0.461 | our license-clean preprocessor @448 — reproduces baseline ✓ |
| 0c | clean448 (control) | pet1  | 15→4 | 19.18 | 0.617 | 0.476 | our preprocessor @448 ✓ |
| **2** | **tall616** | **room1** | 16→4 | **17.55** | **0.729** | 0.474 | +0.02 SSIM, **gaussians 2.6M→3.45M (1.32× denser)**; PSNR flat, LPIPS +0.01. Net win on density/structure |
| **2** | **tall616** | **pet1**  | 15→4 | **19.72** | **0.682** | **0.459** | **clean sweep**: PSNR +0.54, SSIM +0.065, LPIPS −0.017 |
| 2x | tall784 | room1 | — | — | — | — | ❌ OOM (peak 11.3GB). 616 is the VRAM-safe ceiling for 16 views held-out |

**Rank-2 verdict:** adopt `CROP_LONG_CAP=616`. Wins pet1 outright; for room1 it raises surface
density 1.32× and SSIM +0.02 (the stated "low density" axis) at a tiny LPIPS cost. Also removes
the only non-commercial (CC-BY-NC) file from the reconstruct path.

## Ranked experiment queue (from research synthesis)
1. ✅ Poses+held-out eval harness (this table's control)
2. ⏳ Non-square portrait crop 448×616 (recover vertical FOV) — room density
3. ⏳ Scale-needle + SOR floater cleanup (object mode) — pet1 floaters
4. ⏳ AnySplat in-model conf/opacity gates (object mode) — pet1 floaters
5. ⏳ Room view-count / resolution sweep — room density
6. ⏳ gsplat photometric post-opt (Default=room / MCMC=object) — both (biggest lever)
7. ⏳ DBSCAN/projection finishing pass — pet1 floaters (only if residue)
