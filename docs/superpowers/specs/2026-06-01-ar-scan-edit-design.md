# Splatial — Design Spec

> **Status:** Design approved in brainstorming; reshaped per user decisions (camera-only, splat-based, pre-baked edits, modular). Pending final review before the implementation plan.
> **Date:** 2026-06-01
> **Supersedes:** `StreamSplat_Project_Spec.md` (StreamSplat dropped — see §5).

---

## 1. Goal

Scan a small real-world room with a **phone camera (camera-only, no LiDAR)**, reconstruct it as an **editable 3D Gaussian Splatting (3DGS) scene**, and populate it with virtual objects that stay anchored as the viewpoint moves. Objects come from **both** a **pre-built GLB library** and **live voice-driven generation** ("create a 3D chair for me!" → generated GLB placed in the scene). Objects are **editable** (move / rotate / scale / recolor / swap), and the **real scene is editable too** (recolor a wall, remove a real object). The reconstruction is the canvas; **believable placement, generation, and editing are the wow.** End product runs on **AR/AI glasses (Meta lineage)**; the phone is the interim capture device.

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
3. **Two edit targets, both in scope, both pre-baked for the demo:**
   - **Virtual furniture** — place + transform + recolor + swap (easy, modular).
   - **Real scene** — recolor a wall / remove a real object via **Gaussian Grouping** (SAM-2 masks → select/delete/recolor Gaussians, optional LaMa inpaint). Higher risk; computed offline into splat variants the viewer toggles.
4. **Pre-baked edit variants** toggled at demo time (C9) — both furniture and real-scene edits are pre-computed; the `editor` module exposes the same API a live editor would, so going live is a swap, not a rewrite.
5. **Reconstruction GPU = local RTX 4070 Ti (12 GB).** Tight for feed-forward models → cap input views/resolution; **cloud GPU (A10/L4/A100) is the documented fallback** if it OOMs. Per-scene post-optimization (gsplat, ~1–3k steps) and Gaussian Grouping training fit in 12 GB for a small room.
6. **Viewer platform: web / Three.js** — fastest and most reliable for the 2-week demo; mature gsplat renderers. Unity/Meta is the later productization path (the AnySplat reconstruction is platform-agnostic Python and ports regardless).
7. **Objects come from two sources behind one interface:** a **pre-built GLB library** and **live voice→3D generation** (Web Speech API → SDXL-Turbo text→image → TRELLIS-image-large → GLB; all MIT/commercial-safe). **Demo safeguard:** a pre-generated GLB cache keyed by recognized word places objects instantly and deterministically; uncached words fall through to live generation (~30–40s on the 4070 Ti). SF3D (~0.5s) is a lower-latency, lower-fidelity alternative.
8. **Demo strategy = deterministic.** Every "live" moment (real-scene edits, generated objects) has a pre-baked artifact behind it so nothing can stall or fail in front of the CEO; the genuinely-live pipeline runs behind the cache and for post-demo use.

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
| `objects` | Acquire a GLB via one of two providers, place/transform it in the splat frame, surface-snap | `get(query) -> glb` (provider iface), `place(glb, transform) -> SceneObject` | generate, scene_store |
| `generate` | Voice/text → GLB. Web Speech API → SDXL-Turbo → TRELLIS; **pre-generated cache** keyed by word, live fallback | `from_text(prompt) -> glb` | — |
| `editor` | Apply `EditOp`s to objects (transform/recolor/swap) **and** to the real scene (recolor/remove via pre-baked splat variants); same API for live later | `apply(EditOp) -> SplatScene\|SceneObject` | objects, scene_store |
| `viewer` | Render `SplatScene` + `SceneObject`s, free-viewpoint orbit, mic button for voice generation | renders from `scene_store` | scene_store, objects |

Object providers (both implement the same `ObjectProvider` interface):
- `LibraryObjectProvider` — returns a GLB from the pre-built `assets/` library.
- `GeneratedObjectProvider` — returns a GLB from `generate` (cache hit = instant; miss = live ~30–40s).

## 7. Model / asset spine (commercial-safe unless flagged)

| Slot | Pick | License | Note |
|---|---|---|---|
| Reconstruction (primary) | **AnySplat** (`lhjiang/anysplat`) | MIT* | Standard 3DGS + poses from uncalibrated RGB. *Verify VGGT-distillation provenance before commercial ship. |
| Reconstruction (fallback) | **VGGT-1B-Commercial** → **gsplat** | commercial (gated) / Apache-2.0 | If AnySplat quality/VRAM disappoints. |
| Per-scene sharpening | **gsplat** post-opt (1–3k steps) | Apache-2.0 | Hero-scene polish on the 4070 Ti. |
| Object library | **Pre-built GLB** (Sketchfab/Poly Haven, CC0/CC-BY) | per-asset | A few chairs/tables/lamps + pre-generated cache. |
| Speech-to-text | **Web Speech API** (primary); faster-whisper tiny/base (offline backup) | browser / MIT | Mic → text; no GPU VRAM used. |
| Text → image | **SDXL-Turbo** (or FLUX-schnell) | OpenRAIL / FLUX-dev* | ~1s; load/unload before TRELLIS (VRAM). |
| Image → GLB | **TRELLIS-image-large** (`microsoft/TRELLIS-image-large`) | MIT | ~30–40s on 4070 Ti w/ xformers+native spconv+cache-clear. Exports GLB directly. |
| Fast alt (image→GLB) | **SF3D** (`stabilityai/stable-fast-3d`) | Stability Community (<$1M rev) | ~0.5s, ~6GB, coarser textures. |
| Real-scene editing | **Gaussian Grouping** + **SAM 2.1** + Grounding DINO + **LaMa** | Apache-2.0 | Recolor wall / remove real object → **pre-baked splat variants** for the demo. |

**Avoid:** base VGGT-1B, DUSt3R/MASt3R, Fast3R (non-commercial); FLUX-Fill (gated); **TRELLIS.2-4B** (needs 24GB — won't fit the 4070 Ti); **Hunyuan3D-2.1** (restrictive Tencent license: EU/UK/Korea excluded, MAU cap; texture stage >12GB). The "Hunyuan3D = Apache" claim seen online is **wrong** for the weights.

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
   ┌──────────────────────────────────────────────────────┤
   │ objects: place GLB (library OR generated) in splat frame, surface-snap
   │ generate: mic → SDXL-Turbo → TRELLIS → GLB  (cache hit = instant; miss = live ~30s)
   │ editor:  object edits (recolor/swap/move) + real-scene edits (pre-baked splat variants)
   └──────────────────────────────────────────────────────┤
                                                          ▼
                          viewer (web/Three.js): render splat + objects, orbit, mic button
```

Demo loop is deterministic (pre-baked artifacts); live generation/editing runs behind the cache.

## 10. Build phases

Tiered: **[CORE]** must work for the demo to exist; **[WOW]** pre-baked so it's safe, live behind the cache if time allows. If a [WOW] item slips, the demo still stands.

**Phase 0 — Reconstruction spike (day 1–3) [CORE].** Stand up AnySplat on the 4070 Ti (xformers, view/res caps). Phone video of a small room → renderable `.ply` splat. Confirm VRAM; wire cloud fallback. *Exit: a real phone-captured room renders as a splat.*

**Phase 1 — Viewer + anchored placement (day 3–6) [CORE].** Web/Three.js splat viewer, free-viewpoint orbit. Place a library GLB in the splat frame; confirm it **stays anchored as the camera orbits**; surface-snap to the floor. `scene_store` persistence. *Exit: scan → splat → drop a chair → orbit, it stays put.*

**Phase 2 — Object editing (day 6–8) [CORE].** `editor` on virtual objects: recolor / swap / move / rotate / scale. Modular API (same a live editor would use). *Exit: place → edit the object → orbit, reliable.*

**Phase 3 — Voice→3D generation (day 8–11) [WOW].** `generate` module: Web Speech API → SDXL-Turbo → TRELLIS → GLB. **Pre-generate the keyword cache** (chair/table/lamp/plant/…) at full quality → instant placement on stage. Live fallback for uncached words. *Exit: "create a 3D chair" → object appears (cache = instant).*

**Phase 4 — Real-scene editing (day 10–13) [WOW].** Gaussian Grouping + SAM-2 on the room splat: **pre-bake** variants (wall recolored, one object removed+inpainted). Viewer toggles variants. *Exit: toggle "recolor wall" / "remove object" instantly.*

**Phase 5 — Hardening + docs + dry-run (day 13–14) [CORE].** Per-module READMEs/API docs, scene_store reproducibility, full demo dry-run in the real room/lighting.

**Future (post-demo).** Live (non-pre-baked) real-scene editing; on-device AR overlay; port to Meta Quest (OpenXR anchors); camera-only glasses track (VIO + offloaded AnySplat + VPS); metric scale via reference/ARKit; TRELLIS.2/bigger GPU for higher-fidelity generation.

## 11. Risks

| Risk | Mitigation |
|---|---|
| **12 GB VRAM** OOM on AnySplat | Cap views/resolution; cloud GPU fallback documented from day 1. |
| Camera-only splat quality on a phone capture (blur, sparse coverage) | Capture guidance (slow sweep, overlap, good light); gsplat post-opt on the hero scene. |
| Splat + GLB lighting mismatch (furniture looks "pasted on") | Acceptable for POC; note relighting as future. |
| Pre-baked edits must look right at demo res | Bake + review in the real demo room/lighting. |
| **Scope is large for 2 weeks** (recon + viewer + object edit + real-scene edit + voice-gen) | Tiered phases ([CORE] vs [WOW]); everything pre-baked/deterministic; [WOW] items can slip without breaking the demo. |
| Live generation latency/failure (~30–40s; VRAM contention SDXL↔TRELLIS) | Pre-generated keyword cache = instant on stage; load/unload models sequentially; SF3D as fast fallback. |
| Gaussian Grouping per-scene training time on 12GB | Small room only; pre-bake offline well before the demo; toggle variants live. |
| Commercial license (AnySplat distilled from NC VGGT; SF3D <$1M; SDXL OpenRAIL) | Counsel review before ship; VGGT-1B-Commercial / TRELLIS (MIT) fallbacks. **Blocking for product, not demo.** |

## 12. Open questions (resolved unless noted)

- ✅ Viewer = web / Three.js. ✅ Edit scope = both virtual objects and real scene (pre-baked). ✅ Objects = pre-built library + live voice→3D generation.
1. Cloud GPU vendor/instance for the fallback (RunPod/Lambda/Vast A10–A100)? *(decide in Phase 0)*
2. Capture guidance: sweep pattern + frame count for the small room. *(finalize in Phase 0)*
3. Keyword set to pre-generate for the voice demo (chair/table/lamp/plant/…). *(decide before Phase 3)*

## 13. References

- AnySplat — arXiv:2505.23716 — `InternRobotics/AnySplat` (MIT)
- VGGT — arXiv:2503.11651 — `facebook/VGGT-1B-Commercial`; gsplat — `nerfstudio-project/gsplat` (Apache-2.0)
- Gaussian Grouping — arXiv:2312.00732 (Apache-2.0); SAM 2.1 / Grounding DINO / LaMa (Apache-2.0)
- TRELLIS — `microsoft/TRELLIS-image-large` / `TRELLIS-text-*` (MIT); SDXL-Turbo (OpenRAIL); SF3D (`stabilityai/stable-fast-3d`); Web Speech API / faster-whisper
- StreamSplat (rejected; dynamic-only) — arXiv:2506.08862
- Unity Gaussian splat renderers; Three.js gsplat renderers; OpenXR (Khronos); Meta Quest Presence Platform; Project Aria
