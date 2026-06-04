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
2. ✅ Non-square portrait crop 448×616 — DEPLOYED (room SSIM+density, pet1 clean sweep)
3. ✅ Object floater cleanup (oversize + SOR) — DEPLOYED for pet1. Removes isolated stringy
   spray, subject preserved. **Anisotropy gate rejected** (deleted real flat surface splats).
   Connected desk cloud remains (needs rank-6/7 or segmentation).
4. ⏭️ AnySplat in-model conf/opacity gates — DEFERRED (fiddly encoder internals, modest gain;
   rank-6 MCMC achieves the same floater dissolution more reliably)
5. ⏭️ View sweep — PARTIALLY ANSWERED: 20@616 OOMs, 16@616 is the VRAM-optimal point (deployed).
   Full views×res grid deprioritized (VRAM already pins the operating point).
6. ⏳ **gsplat photometric post-opt (Default=room / MCMC=object) — THE big lever, +1.5-4 dB.**
   Needs: persist poses (cameras.npz) + refine.py (gsplat trainer) + eval_ply.py (PLY-render eval).
7. ⏳ DBSCAN/segmentation finishing — pet1 desk removal (only if the object should be isolated)

## Rank-6 post-opt — OOM FIXED, but novel-view overfit (2026-06-04)
Re-investigated the post-opt the user remembered OOMing.
- **OOM is solved**: `tools/postopt.sh` fits **17 init views @ 448², peak 9.9 GB** on the 12 GB
  card (the `no_grad` init patch + `expandable_segments`). The old "~8 views OOMs" note was stale.
- **Metric win**: room1 trainer-held-out **PSNR 12.49→14.28 (+1.79 dB)**, SSIM +0.02, LPIPS better
  (1000 steps, SH0). +2.0 dB at SH1.
- **Two viewer-convention bugs found & fixed** in the refined PLY → viewer path:
  1. **SH degree**: postopt.sh trained at SH1; viewer renders SH0 (reads only f_dc) → washed out.
     Fixed: `--sh-degree 0`.
  2. **Opacity**: gsplat `--save-ply` writes **linear [0,1]**; viewer applies sigmoid (expects
     **logit**) → everything ≥0.5 alpha → fog. Fix: convert opacity linear→logit before the viewer.
- **Remaining issue (the "needle" problem)**: even with conventions fixed, the refined scene shows
  **needle-streak floaters + rainbow colour noise** from free-orbit angles outside the 17-view
  capture trajectory. Detail IS captured (window blinds, wall texture sharpen) but post-opt
  overfits sparse handheld views → looks worse than feed-forward from the viewer's far default
  camera. `scenes/room1po` holds the refined result for inspection.
- **Options to make post-opt win in free-orbit**: (a) needle cleanup on post-opt output (large
  AND high-anisotropy + SOR — distinct from the rejected feed-forward gate); (b) MCMC strategy +
  opacity/scale regularization; (c) denser capture (more overlap); (d) constrain viewer default
  camera near the trajectory. Feed-forward baseline currently looks better for free orbit.

### Open decision (object)
pet1's remaining "background" is the **desk surface** the toy sits on — real geometry, not
floaters. Keeping it = object-in-context; removing it (segmentation/DBSCAN) = isolated turntable
object. Affects rank-7 and what "clean" means. **Ask user.**
