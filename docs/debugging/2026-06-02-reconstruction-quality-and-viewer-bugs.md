# Debugging log — reconstruction quality + viewer bugs (2026-06-02)

Context: the `pet1` capture (slow 15 s orbit around a plush toy) reconstructed with twisted
geometry, see-through/ghosted surfaces, and looked nothing like the AnySplat paper demos. We
ran a 7-dimension adversarial audit (29 agents) + live viewer probing. This log records what
was found, how it was verified, and the fixes — so we don't re-derive it later.

## TL;DR — what was actually wrong

| # | Bug | Root cause | Status |
|---|-----|-----------|--------|
| A | **See-through / ghost haze** | AnySplat exports opacity as a **linear [0,1]** value; the web viewer applies **sigmoid()** on load → every splat renders at alpha 0.50–0.73 (nothing opaque, nothing invisible) | ✅ Fixed |
| B | **Soft / detail-starved geometry** | Capture **double-resizes**: `extract_frames` pre-shrinks 1920×1080 → 448×252, then AnySplat's `process_image` **upscales** the 252 short side back to 448 (blurry). Demo feeds raw 1080p → downsamples sharp | ⏳ Fix identified, not yet applied |
| C | **Prune cull was a no-op** | `optimize_ply` did `_sigmoid(opacity)` on already-linear opacity → all values >0.004 → invisible-splat cull removed nothing | ✅ Fixed implicitly by A (opacity is now logit, so `_sigmoid` is correct) |
| — | **Walk "rotates vertically"** | OrbitControls binds **W/A/S/D to panning** (`enablePan:true`); walk.js also owns translation → move keys double-fire (W moves forward **and** pans up) | ✅ Fixed |
| — | Tilted/awkward orbit framing | `up`/`scale_hint` are **hardcoded** `[0,1,0]`/`1.0`; AnySplat's `pred_context_pose` (true orientation) is **discarded** | ⏳ Open (viewer framing only — not twist/PSNR) |

**Refuted (do NOT chase):** "exploded/NaN gaussians" — the PLY is 100% finite & bounded.
"single object is out-of-distribution" — AnySplat trains on CO3Dv2 and ships an object-orbit
demo. "16 views too sparse" — matches the demo's ~1 fps sampling. Motion blur — VoL 301–740,
all sharp. The 448×448 square center-crop is AnySplat's **intended** input contract, not a bug.

## Bug A — opacity double-activation (the big one)

**Chain (all verified against source + data):**
- `external_AnySplat/src/model/encoder/anysplat.py:229` `map_pdf_to_opacity` → values in [0,1].
- `external_AnySplat/src/model/ply_export.py:63` writes opacity **verbatim** (scales get `.log()`, opacity doesn't).
- `web/node_modules/@mkkellogg/gaussian-splats-3d/.../gaussian-splats-3d.module.js` → `1/(1+Math.exp(-opacity))` on load.

**How verified:**
```bash
PY=/home/liylo/anaconda3/envs/anysplat/bin/python
# opacity distribution of the produced PLY
$PY -c "import numpy as np;from plyfile import PlyData;\
o=np.asarray(PlyData.read('scenes/pet1/scene.ply')['vertex']['opacity'],float);\
print(o.min(),np.median(o),o.max(),'in[0,1]=',((o>=0)&(o<=1)).mean())"
# -> 0.0 0.05 0.995 in[0,1]=1.0   => LINEAR probability, not logit
grep -n 'opacit\|\.log()' external_AnySplat/src/model/ply_export.py
grep -o '1 / (1 + Math.exp(-rawSplat\[OPACITY\]))' web/node_modules/@mkkellogg/gaussian-splats-3d/build/gaussian-splats-3d.module.js
```

**Fix:** store the logit so the viewer's sigmoid recovers true alpha.
- Export path: `modules/reconstruct/anysplat_provider.py::_export_ply` now converts
  `op_logit = log(clamp(o,1e-6,1-1e-6)/(1-...))` before `export_ply`.
- Existing scenes repaired in place by **`tools/fix_opacity.py`** (idempotent — skips PLYs
  already in logit space; keeps a `.ply.bak`). Run: `python tools/fix_opacity.py scenes/<id>`.
- Result: pet1 went from "everything 50–73% haze" to 2.2% solid / 62.8% invisible — i.e. the
  toy/desk/monitor are now solid and the fog is gone. (The high invisible-fraction reflects
  the model's genuinely low confidence on the furry/low-texture subject — a capture problem, not a display one.)

## Walk "rotates vertically" — diagnosis method

The turn math was *suspected* wrong but turned out **correct**. Diagnosed by probing the live
viewer with Playwright instead of guessing:
```js
// read screen-up direction + simulate a key, measure which axis the target moves on
const colY = new THREE.Vector3().setFromMatrixColumn(cam.matrixWorld, 1)  // ≈ world +Y => screen upright
window.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyQ'}))          // turn-left
// after ~45 frames: targetDelta = [0.948, 0, -0.675]  => y=0 => HORIZONTAL yaw (correct)
// then W (forward) BEFORE fix drifted vertically because OrbitControls.enablePan + keys{WASD} panned too
```
Found `viewer.controls.keys = {LEFT:KeyA, UP:KeyW, RIGHT:KeyD, BOTTOM:KeyS}`, `enablePan:true`.
**Fix:** `viewer.controls.enablePan = false` in `web/src/walk.js` (walk owns translation). After:
forward moves camera+target together with no independent pan drift.

**Lesson:** for "the viewer feels wrong" bugs, probe `window.__viewer` (camera/controls/matrix)
and simulate input to *measure* the axis, rather than reasoning about the math blind.

## Capture protocol for the next shoot (object-centric)

pet1's input was the limiter (furry textureless subject, specular RGB-lit cluttered desk,
object near frame edges). For a good object scan:
1. **Native resolution**, do not pre-shrink (see Bug B fix below).
2. Keep the subject in the **central ~56%** of a 16:9 frame (AnySplat center-crops to square).
3. **Matte** subject + props; **kill RGB LEDs / monitors / colored light**; lock AE/AWB/focus.
4. **Static, textured** background (or mask it) — pick one, not both.
5. Orbit the **camera** around a **still** object, slow ~20–30 s, vary height; real parallax (don't spin in place).

## Settings still to change (identified, not yet applied)

- **Bug B:** `modules/reconstruct/cli.py` extract at `long_side≥960` (or native) so the short
  side stays ≥448 and `process_image` downsamples sharp pixels instead of upscaling mush.
  Make `resize_long_side` a no-op when `long_side<=0`. (Does NOT increase VRAM — model input is fixed 448².)
- **up/scale:** persist `pred_context_pose` in `anysplat_provider.py`, derive `up` from camera
  axes, wire `scene.up` through `main.js`/`splatViewer.js`/`walk.js` (viewer ignores it today).
- **Post-opt:** orphaned (`tools/postopt.sh` exists but isn't in the default path). Gate behind `REFINE=1`.
- **Re-measure PSNR on pet1** — no pet1 eval exists; the 7.95→9.58 numbers are room2 only.

Full audit report: workflow `splatial-quality-audit` (run wf_7a1b8462-4d9).
