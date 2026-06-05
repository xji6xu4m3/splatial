# Reconstruction quality experiments — results log

## ★ VERDICT (2026-06-04): feed-forward is the hero; per-scene post-opt is a dead end on dense scenes

After a cloud-A100 campaign (48-view feed-forward → gsplat `default` post-opt → MCMC → MCMC+opacity-reg),
held-out PSNR climbed **22.6 → 27.4 → 28.1 → 28.5** — but a **free-orbit screenshot dome**
(`web/tools/orbit-shots.mjs`, 8 azimuths × 2 elevations) shows the opposite ranking: **feed-forward is
smooth and coherent from every orbit angle; every post-opt variant is haloed in needle-spray + rainbow
speckle from every angle** (see `web/orbit/AB_eyelevel.jpg`). The held-out PSNR is **on-trajectory
INTERPOLATION** (`eval_heldout.py` splits `idx % K` → targets sit between context frames on the same
arc) and is **decorrelated from / inverts free-orbit realism**. We optimized the wrong number.

**Root cause** (full analysis: `docs/analysis/2026-06-04-postopt-vs-feedforward-rootcause.md`): per-scene
3DGS is under-constrained MLE that overfits the sparse handheld trajectory; needles/floaters/gaps/speckle
are null-space artifacts that render the capture path perfectly but break off-axis. Feed-forward is an
amortized MAP estimate carrying a learned prior → lower on the bogus metric, but generalizes. AnySplat's
paper only claims post-opt helps where feed-forward is *weak* (16-view); our 48-frame dense scene is
exactly where it does not.

**Decisions:**
- **Feed-forward AnySplat is the shipped hero for BOTH phone (`hires`, 1.1M mobile) and desktop
  (`hires_full`, full ~11.5M).** Post-opt is retired (experiment scenes moved to `scenes/.trash`).
- **Realism is now judged by the orbit dome (`orbit-shots.mjs`) + `eval_heldout.py --split tail`
  (extrapolation ePSNR), NEVER by interpolation iPSNR alone.**
- **Forward path = a better PRIOR, not post-opt.** Next experiment: swap the feed-forward model for
  **YoNoSplat** (pose-free, std-3DGS, MIT code, ~+3–5 dB indoors vs AnySplat; Pi3-backbone weights are
  non-commercial → demo-safe, product-flagged), A/B'd against AnySplat on the orbit ruler.

The PSNR table below is retained as a record but its ranking is **misleading for free-orbit** (see above).

---

Metric: held-out-view PSNR/SSIM/LPIPS (every 5th selected frame held out, reconstruct from the
rest, render the held-out poses with AnySplat's decoder). Harness: `experiments/eval_heldout.py`
(`--split interleave` = iPSNR interpolation, default; `--split tail` = ePSNR extrapolation).
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

### Post-opt MCMC + regularization (2026-06-04) — did NOT fix the haze
Tried `simple_trainer.py mcmc` (opacity_reg=scale_reg=0.01, SH0, 1000 steps) to dissolve the
residual room haze/needles.
- PSNR 12.46→**13.54 (+1.08 dB)** — *less* than DefaultStrategy (+1.79).
- Regularization too weak to matter: needle anisotropy median **61 vs 69** (≈unchanged),
  p90 actually higher; mean alpha 0.59→0.54. Visually still hazy from free-orbit.
- **Verdict: post-opt is not worth it on these sparse (17-view) handheld captures.** It improves
  the held-out metric but overfits the trajectory → looks worse than feed-forward from the
  viewer's free-orbit camera. Neither Default nor MCMC produces a clean free-orbit result.
- **DECISION: post-opt DISABLED as default.** It was never wired into the deployed CLI, so the
  shipped scenes (scenes/room1, scenes/pet1) are already feed-forward-only. `tools/postopt.sh` +
  `tools/postopt_to_scene.py` remain as an OPTIONAL offline "hero scene" tool for when capture is
  dense enough; the OOM + 3 convention fixes make them correct if revisited. Experimental scenes:
  room1po (Default+clean), room1mcmc (MCMC+clean) — kept for reference, not deployed.


## 784 vs 616 crop, fixed view budget (2026-06-04) — views >> FOV
Tested whether the full-FOV 448×784 crop (which OOMs at 16 views, forcing fewer) beats 448×616@16.
Matched A/B on the same 10 frames / 7 context views (isolates FOV only):
- 616: PSNR 11.90 / SSIM 0.626 / LPIPS 0.610
- 784: PSNR 11.56 / SSIM 0.657 / LPIPS 0.628  (≈wash: +SSIM, −PSNR)
But view count dominates: 16 views → 17.55 PSNR vs 7 views → ~11.6 (**−5.6 dB**). Since 784 forces
the view count DOWN (OOMs at 16), the coverage lost costs ~15× more than the FOV gained.
**Decision: keep 448×616 @ 16 views. Do NOT trade views for the taller crop.**

### Open decision (object)
pet1's remaining "background" is the **desk surface** the toy sits on — real geometry, not
floaters. Keeping it = object-in-context; removing it (segmentation/DBSCAN) = isolated turntable
object. Affects rank-7 and what "clean" means. **Ask user.**
