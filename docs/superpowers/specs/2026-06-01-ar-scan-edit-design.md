# Splatial — Design Spec

> **Status:** Design approved in brainstorming; reshaped per user decisions (camera-only, splat-based, pre-baked edits, modular). Pending final review before the implementation plan.
> **Date:** 2026-06-01
> **Supersedes:** `StreamSplat_Project_Spec.md` (StreamSplat dropped — see §5).

---

## 1. Goal

Scan a small real-world room with a **phone camera (camera-only, no LiDAR)**, reconstruct it as an **editable 3D Gaussian Splatting (3DGS) scene**, and place **virtual furniture that stays anchored** as the viewpoint moves — with the furniture being **editable** (move / rotate / scale / recolor / swap). The reconstruction is the canvas; **believable placement + editing is the wow.** End product runs on **AR/AI glasses (Meta lineage)**; the phone is the interim capture device.

## 2. Confirmed constraints

| # | Constraint |
|---|---|
| C1 | End product = AR glasses (Meta: Quest 3 → Orion/Meta glasses). Phone is interim. |
| C2 | Demo wow = believable placement + editing of virtual furniture, anchored. Live-reconstruction speed is *not* the priority. |
| C3 | Mostly static scenes, minor incidental motion. |
| C4 | < 2 weeks to the CEO demo. De-risked, off-the-shelf components. |
| C5 | Commercial product path → prefer MIT/Apache models; flag every non-commercial dependency. |
| C6 | **Camera-only (no LiDAR).** Reconstruction is purely from RGB phone video. |
| C7 | **Splat-based.** 3DGS is the scene representation (not mesh). |
| C8 | **Modular design.** Each module has a clear data contract + README/API doc, so pieces scale and bug-fix independently. |
| C9 | **Pre-baked edits for the demo**, but architected so live editing drops in without rework. |

## 3. Headline decisions

1. **Single camera-only splat pipeline.** Phone video → frames → **AnySplat (MIT)** → 3DGS scene → splat **viewer** with placed/editable furniture. No ARKit/LiDAR needed for the demo.
2. **Demo is a free-viewpoint viewer**, not live on-device AR. Furniture placed in the splat's coordinate frame stays anchored *because it is rendered in the same 3D scene* — anchoring is automatic, no SLAM needed for the POC.
3. **Edit target for the demo = the virtual furniture** (transform + recolor + swap), which is trivial to manipulate and modular. Editing the *real* scene (recolor a wall, remove a real object via Gaussian Grouping) is a **later** feature, not in the 2-week scope.
4. **Pre-baked edit variants** toggled at demo time (C9); the editing module exposes the same API a live editor would, so going live is a swap, not a rewrite.
5. **Reconstruction GPU = local RTX 4070 Ti (12 GB).** Tight for feed-forward models → cap input views/resolution; **cloud GPU (A10/L4/A100) is the documented fallback** if it OOMs. Per-scene post-optimization (gsplat, ~1–3k steps) fits comfortably in 12 GB for a small room and sharpens the hero scene.
6. **Viewer platform: TBD this review** — Unity (preserves Meta/Quest path, has Gaussian-splat packages) vs. web/Three.js (fastest, most reliable for a 2-week demo). See §12 Q1.

## 4. Reconstruction tracks

| Track | Source | Role | Status |
|---|---|---|---|
| **Primary — camera-only splat** | Phone RGB video → AnySplat → 3DGS | The demo. Offline reconstruction on the 4070 Ti (cloud fallback). | Weeks 1–2 |
| **Future — on-device AR / glasses** | On-glasses VIO + offloaded AnySplat/VGGT + VPS persistence; built to OpenXR | The product (Meta glasses). | Future |

Optional scale aid: if metric scale is ever needed, align AnySplat's up-to-scale output to a known reference or (on a Pro iPhone) ARKit poses via a single Sim(3) factor. Not required for the viewer demo (consistent relative scale is enough to place furniture).

## 5. Why StreamSplat is dropped (on record)

StreamSplat (arXiv:2506.08862) is best-in-class at **online dynamic streaming** — the axis we deprioritized — and pays with the properties we need: **orthographic / non-metric** (nothing to anchor or edit cleanly), **dynamic 4D overhead** on a static room, **not a drop-in for splat editors**, and **research-grade** (custom CUDA rasterizer, A100, CC-BY-NC depth backbone, unlicensed repo) — disqualifying on C4/C5. **When it would win:** capturing *moving* content for free-viewpoint replay. Optional residual role: a decoupled "watch the room come alive" novelty clip. Not in scope.

## 6. Module boundaries & contracts (C8)

Six modules, each with a README documenting its public API and data contract. They communicate only through the shared data types below — never reach into each other's internals.

```
capture ──frames──▶ reconstruct ──SplatScene──▶ scene_store ◀──persist── objects/editor
                                       │                                      │
                                       └────────────── viewer ◀──────────────┘
                                                   (renders SplatScene + SceneObjects)
```

**Shared data contracts**
```
SplatScene   { id, gaussians_ref(.ply), bbox, up_vector, scale_hint, source_meta }
SceneObject  { id, glb_ref, transform(pos,rot,scale), material_overrides, scene_id }
EditOp       { id, target(object_id|scene), kind(transform|recolor|swap|remove), params }
```

| Module | Responsibility | Public API (sketch) | Depends on |
|---|---|---|---|
| `capture` | Phone video → ordered frames (sampling, dedup, resize) | `extract_frames(video) -> [Frame]` | — |
| `reconstruct` (`SceneProvider`) | Frames → `SplatScene`. **AnySplat** impl now; VGGT impl later. Never leaks backend internals. | `reconstruct(frames) -> SplatScene` | capture |
| `scene_store` | Persist/load splats, placed objects, edit ops (reproducible scenes) | `save(scene)/load(id)/apply(EditOp)` | — |
| `objects` | Place/transform GLB furniture in the splat frame; surface snap | `place(glb, transform) -> SceneObject` | scene_store |
| `editor` | Apply `EditOp`s (transform/recolor/swap; pre-baked now, live later) | `apply(EditOp) -> SceneObject` | objects, scene_store |
| `viewer` | Render `SplatScene` + `SceneObject`s, free-viewpoint orbit | renders from `scene_store` | scene_store |

## 7. Model / asset spine (commercial-safe unless flagged)

| Slot | Pick | License | Note |
|---|---|---|---|
| Reconstruction (primary) | **AnySplat** (`lhjiang/anysplat`) | MIT* | Standard 3DGS + poses from uncalibrated RGB. *Verify VGGT-distillation provenance before commercial ship. |
| Reconstruction (fallback) | **VGGT-1B-Commercial** → **gsplat** | commercial (gated) / Apache-2.0 | If AnySplat quality/VRAM disappoints. |
| Per-scene sharpening | **gsplat** post-opt (1–3k steps) | Apache-2.0 | Hero-scene polish on the 4070 Ti. |
| Furniture | **Fixed GLB library** (Sketchfab/Poly Haven, CC0/CC-BY) | per-asset | A few chairs/tables/lamps for the demo. |
| Furniture generation (future) | TRELLIS / TRELLIS.2 | MIT | Image→GLB on demand. |
| Real-scene editing (future) | Gaussian Grouping; SAM 2.1 + Grounding DINO; LaMa | Apache-2.0 | Recolor wall / remove real object. Not in 2-week scope. |

**Avoid for product:** base VGGT-1B, DUSt3R/MASt3R, Fast3R (non-commercial); FLUX-Fill (gated); Hunyuan3D territory/MAU clauses.

## 8. AnySplat verification (arXiv:2505.23716, confirmed)

- ✅ Phone-camera-only RGB input (uncalibrated, unposed, 1→hundreds of views).
- ✅ Outputs **standard perspective 3DGS** + intrinsics/extrinsics + depth, one pass, seconds.
- ⚠️ **Not metric** out of the box (up-to-scale; distilled from VGGT). Fine for a viewer demo; align to a reference only if metric is needed later.
- ⚠️ **Batch, not streaming** — capture-then-reconstruct. Fine (live tracking not needed for the viewer).
- ⚠️ **Static model** — minor motion → ghosting on moving parts (acceptable, C3).
- ⚠️ **VRAM: 12 GB (4070 Ti) is tight.** Cap views (~8–24) and resolution (≤448px long side); fall back to cloud GPU for larger scans. Differentiable voxelization caps Gaussian count and memory plateaus with views (paper Fig 5).

## 9. Data flow (demo)

```
phone video (small room) ──▶ capture: extract frames (8–24, ≤448px)
                                  │
                                  ▼
                          reconstruct: AnySplat ──▶ SplatScene (.ply) ──▶ scene_store
                                                          │
                                  objects: place furniture GLB in splat frame
                                  editor:  pre-baked variants (recolor / swap / move)
                                                          │
                                                          ▼
                          viewer: render splat + furniture, free-viewpoint orbit
```

All offline → no neural inference in the live demo loop.

## 10. Build phases

**Phase 0 — Reconstruction spike (day 1–3).** Stand up AnySplat on the 4070 Ti. Feed a phone video of a small room; produce a renderable `.ply` splat. Confirm VRAM headroom and pick view/resolution caps; wire the cloud fallback. *Exit: a real phone-captured room renders as a splat.*

**Phase 1 — Viewer + anchored placement (day 4–8).** Splat viewer (platform per §12 Q1) with free-viewpoint orbit. Place a furniture GLB in the splat frame; confirm it **stays anchored as the camera orbits**. Surface-snap to the floor. *Exit: scan → splat → drop a chair → orbit, it stays put.*

**Phase 2 — Editing the furniture (day 9–12).** `editor` module with pre-baked variants: recolor the furniture, swap to a different GLB, move/rotate/scale. Modular API identical to a future live editor. Polish UI in the real demo room. *Exit: the CEO loop — scan → place → edit the furniture → walk around — runs reliably.*

**Phase 3 — Hardening + docs (day 13–14).** Per-module READMEs/API docs, scene_store reproducibility, demo dry-run in real lighting.

**Future (post-demo).** Real-scene splat editing (Gaussian Grouping); on-device AR overlay; port to Meta Quest (OpenXR anchors); camera-only glasses track (VIO + offloaded AnySplat + VPS); TRELLIS furniture generation; metric scale via reference/ARKit.

## 11. Risks

| Risk | Mitigation |
|---|---|
| **12 GB VRAM** OOM on AnySplat | Cap views/resolution; cloud GPU fallback documented from day 1. |
| Camera-only splat quality on a phone capture (blur, sparse coverage) | Capture guidance (slow sweep, overlap, good light); gsplat post-opt on the hero scene. |
| Splat + GLB lighting mismatch (furniture looks "pasted on") | Acceptable for POC; note relighting as future. |
| Pre-baked edits must look right at demo res | Bake + review in the real demo room/lighting. |
| Viewer-platform risk (Unity splat rendering fiddly) | Web/Three.js fallback keeps the demo safe; Unity is the productization path. |
| Commercial license (AnySplat distilled from NC VGGT + NC training data) | Counsel review before ship; VGGT-1B-Commercial fallback. **Blocking for product, not demo.** |

## 12. Open questions

1. **Viewer platform — Unity vs web/Three.js?** Unity preserves the Meta/Quest path but splat rendering is heavier to set up; web is the fastest, most reliable 2-week demo. *(Decide this review.)*
2. Cloud GPU vendor/instance for the fallback (RunPod/Lambda/Vast A10–A100)?
3. Capture guidance: how the user records the small room (sweep pattern, frame count) — finalize in Phase 0.

## 13. References

- AnySplat — arXiv:2505.23716 — `InternRobotics/AnySplat` (MIT)
- VGGT — arXiv:2503.11651 — `facebook/VGGT-1B-Commercial`; gsplat — `nerfstudio-project/gsplat` (Apache-2.0)
- Gaussian Grouping (future) — arXiv:2312.00732 (Apache-2.0); SAM 2.1 / Grounding DINO / LaMa (Apache-2.0); TRELLIS (MIT)
- StreamSplat (rejected; dynamic-only) — arXiv:2506.08862
- Unity Gaussian splat renderers; Three.js gsplat renderers; OpenXR (Khronos); Meta Quest Presence Platform; Project Aria
