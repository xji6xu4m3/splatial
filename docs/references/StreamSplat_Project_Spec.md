# Interactive Real-World Scene Capture & Decoration — Project Build Spec

> **Purpose of this document:** A self-contained design + build specification to be used as a prompt for a coding AI. It defines the goal, requirements, architecture, tech stack, build phases, key interfaces, and known risks for a proof-of-concept that scans a real space, reconstructs it as a 3D Gaussian scene, and lets a user place/edit virtual objects that stay anchored in the geometry as the viewpoint moves.

---

## 1. Goal

Build a proof-of-concept (POC) where a user:

1. **Scans** a real-world space (e.g., a closet, a room corner) by recording a short video with a **phone camera** (later: AR glasses camera).
2. Sees the space **reconstructed as a navigable 3D Gaussian Splatting (3DGS) scene** with as little delay as possible (target: "near-live").
3. **Adds virtual objects** (decorations, furniture) onto surfaces, and the objects **stay correctly anchored in the 3D geometry as the user moves the viewpoint**.
4. *(Later stage)* **Edits the real scene** — recolor surfaces, remove/replace existing objects.

The POC is a demo for a CEO. Priorities, in order: (1) the "wow" of live-ish faithful reconstruction of a *real* space, (2) persistent, believable object placement, (3) visual quality, (4) path to AR glasses.

**Reconstruction engine of choice:** [StreamSplat](https://github.com/DSL-Lab/StreamSplat) (ICLR 2026) — a fully feed-forward, online, camera-free dynamic 3DGS model. Chosen because it is the closest available open method to "Approach B that is nearly live": it produces a 3DGS scene from uncalibrated monocular video in a single feed-forward pass (~0.049s/frame on an A100), with no per-scene optimization and no camera calibration step.

---

## 2. Non-Goals (explicitly out of scope for the POC)

- On-device (phone/glasses) reconstruction. Reconstruction runs in the **cloud on a GPU**; the phone is a capture + display client.
- Physically accurate relighting/shadowing of inserted objects (nice-to-have, not required for v1).
- Editing objects after placement (color, position, etc.).
- Production-grade AR glasses deployment (we only keep the architecture *glasses-ready*).
- Metrically perfect measurement of the room.

---

## 3. Core Requirements

### Functional
- **F1.** Accept a short monocular video (phone) as input; no calibration / no COLMAP required from the user.
- **F2.** Produce a navigable 3DGS scene of the captured space.
- **F3.** Render the scene interactively (free-viewpoint orbit/look-around) in a viewer (web first).
- **F4.** Insert a 3D object (mesh or splat) into the scene's coordinate frame; the object persists across viewpoints.
- **F5.** Allow basic manipulation of the inserted object: translate, rotate, scale, place-on-surface.
- **F6 (Stage 2).** Segment and edit existing scene content: recolor a surface, remove/replace an object.
- **F7.** Stream the rendered view to a thin client (phone now; glasses later).

### Non-Functional
- **N1.** Time from "finish scanning" to "navigable scene": target < 30s for POC (StreamSplat is feed-forward, so this is realistic on a single modern GPU).
- **N2.** Reconstruction backend MUST be swappable (see §6, the `Reconstructor` interface). Do not hard-couple the rest of the system to StreamSplat's internals.
- **N3.** Keep a clean boundary between cloud compute (reconstruction) and client (capture/display), so glasses can later replace the phone.
- **N4.** Track licenses of all models/data; flag anything non-commercial (see §9).

---

## 4. Understanding StreamSplat (what we're building on)

**Source:** Wu, Yan, Yi, Wang, Liao. *StreamSplat: Towards Online Dynamic 3D Reconstruction from Uncalibrated Video Streams.* ICLR 2026. arXiv:2506.08862. Repo: https://github.com/DSL-Lab/StreamSplat . Project: https://streamsplat3d.github.io/

**What it is:** A fully feed-forward framework that turns an uncalibrated monocular video stream of arbitrary length into a **dynamic** 3DGS representation, online (frame-by-frame), with no per-scene optimization.

**How it works (key mechanisms):**
- **Probabilistic 3D Gaussian encoding:** per-frame, predicts pixel-aligned 3D Gaussians; samples a truncated-normal distribution for each Gaussian's position offset instead of regressing directly (stabilizes convergence, avoids local minima).
- **Orthographic canonical space:** uses a shared orthographic canonical space instead of recovering per-scene perspective camera intrinsics/poses. Camera motion + perspective are absorbed into the Gaussian dynamics. This is what makes it camera-free / calibration-free.
- **Bidirectional deformation field:** predicts forward + backward motion between the canonical state and the current frame; handles emerging/vanishing content and limits long-term drift.
- **Adaptive Gaussian fusion:** soft-matches and propagates persistent Gaussians across frames for temporal coherence.
- **Frozen pretrained backbones:** Depth Anything V2 (monocular depth, ViT-L checkpoint) + DINOv2 (vision features). A Transformer Static Encoder + Dynamic Decoder are the trained parts.

**Performance / specs (from paper):**
- ~0.049s per frame end-to-end on a **single NVIDIA A100** (~20 fps); ~1200× speedup vs optimization-based dynamic methods.
- Trained on 8×A100 for ~3 days. Input resolution 288×512; evaluation at 256×256.
- Trained/evaluated on RealEstate10K + CO3Dv2 (static) and DAVIS + YouTube-VOS (dynamic).

**What the repo provides:** conda `environment.yml`, a custom CUDA **orthographic** Gaussian rasterizer (`submodules/diff-gaussian-rasterization-orth`), two-stage training (`train.py` → `train_decoder.py`), inference (`splat_inference.py`, takes RGB frames + precomputed depth maps), and a **pretrained checkpoint** (Google Drive). A depth-preprocessing script (`preprocess_depth_davis.py`).

**What the repo does NOT provide (we must build):** an interactive viewer/UI, object insertion, scene editing, surface detection, AR anchoring, video→frames+depth ingestion for arbitrary phone input, and any client app.

---

## 5. Critical Risks & Design Decisions (READ BEFORE BUILDING)

These are the reasons the architecture is modular. Each risk has a mitigation baked into the design.

| # | Risk | Why it matters here | Mitigation in this design |
|---|------|---------------------|---------------------------|
| R1 | **StreamSplat is a *dynamic* (4D) model; our scene is *static*.** | Dynamic machinery is unnecessary for a still closet and may add noise. | Treat StreamSplat as ONE reconstructor behind the `Reconstructor` interface (§6). For a static scene we can also extract a single canonical Gaussian set, or swap in a static feed-forward model (NoPoSplat/AnySplat) without touching downstream code. |
| R2 | **Orthographic canonical space — no true perspective camera poses.** Paper flags "camera model misalignment in close-range scenes with strong perspective effects." A closet is close-range. | Precise object placement and especially **AR-glasses anchoring** want metric, perspective-correct geometry. | (a) Keep object placement in StreamSplat's canonical frame for the v1 viewer demo. (b) For AR anchoring (later), add a **separate static, perspective-correct reconstruction path** (classic 3DGS via COLMAP, or a pose-recovering feed-forward model) used specifically for anchoring. Do NOT assume StreamSplat output is metric. |
| R3 | **Low resolution (288×512 / 256×256).** | May underwhelm visually in a CEO demo. | For the "hero" still shots, allow a higher-quality static reconstruction path. Use the StreamSplat path for the live "watch it build" moment; use a higher-res static splat for the polished decorate-and-show moment. |
| R4 | **Commercial-license risk.** Repo has no explicit license; Depth Anything V2 ViT-L is CC-BY-NC; CO3Dv2 training data is CC-BY-NC. | This is for a paid/company project. | For POC/demo only, fine. Before any commercial use: switch depth to Depth Anything V2 **ViT-S/B (Apache-2.0)**, confirm/obtain repo license from authors, and avoid CC-BY-NC training data if retraining. Track this as a blocking item for productization. |
| R5 | **Cloud GPU dependency (A100-class), not phone.** | "Live on phone" really means cloud inference + streaming. | Architect cloud reconstruction service + thin client from day one (§6). This is also exactly what AR glasses will need (offload). |
| R6 | **Editing tools assume standard perspective splats + COLMAP.** GaussianEditor / Gaussian Grouping expect a normal 3DGS scene. | StreamSplat output is orthographic/canonical/dynamic → not a drop-in for these tools. | Stage-2 editing runs on the **static perspective-correct splat** (R2 path), not on StreamSplat's raw output. Keep editing decoupled. |

**Headline decision:** Build a **two-track reconstruction design**:
- **Track LIVE** = StreamSplat → instant camera-free preview as the user sweeps ("look, it's reconstructing your closet live").
- **Track EDIT** = a static, perspective-correct splat of the same capture → the scene we actually decorate, edit, and (later) anchor in AR.

For v1 you may ship Track LIVE only (place objects in canonical space) and add Track EDIT in Phase 3. The interface in §6 makes both look identical to the rest of the app.

---

## 6. Architecture

```
[Phone client]                         [Cloud GPU service]                       [Phone client]
 capture video  ──upload──▶  ingest → frames + depth (Depth Anything V2)
                                     │
                                     ├── Track LIVE:  StreamSplat feed-forward  ─┐
                                     │                  (dynamic/canonical 3DGS)  │
                                     │                                           ├──▶ Gaussian scene (3DGS)
                                     └── Track EDIT (Phase 3): static recon ──────┘        │
                                          (COLMAP + 3DGS, or NoPoSplat/AnySplat)           │
                                                                                           ▼
                                                              Scene store  ◀── object insertion / editing ops
                                                                                           │
                                                                            render (orthographic or perspective)
                                                                                           │
                                                                  ◀────── stream frames / send splat ──────▶  viewer
```

### Key module: `Reconstructor` interface (the swappable boundary — N2)
Define a single abstraction so StreamSplat is replaceable:

```python
class Reconstructor(Protocol):
    def reconstruct(self, frames: list[Image], depths: list[Image] | None) -> GaussianScene:
        """Return a GaussianScene (positions, rotations, scales, opacities, colors,
        + coordinate-frame metadata: {'projection': 'orthographic'|'perspective',
        'metric': bool, 'poses': optional}). Must NOT leak backend internals."""
```

Implementations:
- `StreamSplatReconstructor` — wraps `splat_inference.py`; sets `projection='orthographic'`, `metric=False`.
- `StaticGSReconstructor` (Phase 3) — COLMAP + official 3DGS, or a pose-recovering feed-forward model; sets `projection='perspective'`, `metric=True`.

Everything downstream (viewer, object insertion, editing, AR) consumes `GaussianScene` and branches only on its metadata flags.

### Components
1. **Capture client (phone, web or native):** record video, upload to cloud. (Later: ARKit/ARCore to also capture poses/depth for Track EDIT.)
2. **Ingestion:** video → frames; run Depth Anything V2 to produce depth maps (StreamSplat consumes RGB + depth).
3. **Reconstruction service:** GPU service exposing `reconstruct()`; hosts StreamSplat (and later the static path). Returns/stores a `GaussianScene`.
4. **Scene store:** persists the splat + inserted objects + edit ops (so the scene is reproducible and editable).
5. **Object library + inserter:** place 3D assets (start with a few GLB meshes; optionally generate via an image-to-3D model). Handle transform + simple surface snapping.
6. **Viewer (web first):** render the Gaussian scene + inserted objects together so objects stay anchored across viewpoints (F4). Use a WebGL splat renderer. Must render in the scene's projection (orthographic for StreamSplat output).
7. **Editor (Phase 4):** segmentation + recolor/remove on the static perspective splat.
8. **Streaming (Phase 5):** stream rendered frames to phone; later anchor into AR via ARKit/ARCore.

---

## 7. Tech Stack

**Reconstruction (cloud):**
- StreamSplat (https://github.com/DSL-Lab/StreamSplat) — primary engine. Use the provided pretrained checkpoint.
- Depth Anything V2 — monocular depth (use ViT-L for POC; **switch to ViT-S/B Apache-2.0 for any commercial path**).
- DINOv2 — vision features (pulled in by StreamSplat).
- Custom orthographic CUDA rasterizer (ships with StreamSplat repo).
- *(Phase 3, Track EDIT)* COLMAP + official 3D Gaussian Splatting (`graphdeco-inria/gaussian-splatting`), or a pose-free feed-forward static model (NoPoSplat / AnySplat) — evaluate both.

**Object insertion / assets:**
- Start with static GLB/OBJ assets (a small decoration library).
- Optional: image-to-3D generation (e.g., Hunyuan-3D via a hosted API) to create decorations from a reference image.

**Scene editing (Stage 2 / Phase 4):**
- Gaussian Grouping (segment + recolor/remove; arXiv:2312.00732) — primary for editing real content.
- GaussianEditor (CVPR 2024; arXiv:2311.14521) — alternative, esp. for guided add/remove.
- SAM (masks) as needed by the above.

**Viewer / client:**
- Web viewer: a WebGL/Three.js Gaussian-splat renderer (e.g., a `gsplat`-style renderer) + standard GLTF loader for inserted meshes. Single-page app; no browser localStorage for state (keep state in memory / backend).
- Phone: browser first; native (ARKit/ARCore) when adding AR anchoring.
- *(Mobile render later)* Mobile-GS-style techniques for smooth on-phone rendering of the finished splat.

**Backend / infra:**
- Python service (FastAPI or similar) wrapping the `Reconstructor`.
- GPU host: a single A100/L40S/4090-class GPU is enough for POC inference.
- Job/result storage for `GaussianScene` artifacts.

**AR (later, Track EDIT only):**
- ARKit (iOS) / ARCore (Android) for live pose + plane detection to anchor the decorated scene into the real room.

---

## 8. Build Phases (milestones for the coding AI)

**Phase 0 — Repro StreamSplat (de-risk first).**
- Clone repo, create the conda env, build the `diff-gaussian-rasterization-orth` submodule, download the pretrained checkpoint and Depth Anything V2 checkpoint.
- Run `splat_inference.py` on a sample sequence; confirm it produces a renderable dynamic 3DGS result. Document GPU + runtime.
- **Exit criteria:** a reconstructed splat from sample input, rendered to images/video.

**Phase 1 — Ingest real phone capture.**
- Pipeline: phone video → frames → Depth Anything V2 depth → StreamSplat → `GaussianScene`.
- Wrap StreamSplat behind `StreamSplatReconstructor` implementing the `Reconstructor` interface.
- **Exit criteria:** record a closet on a phone, get a navigable splat in the viewer.

**Phase 2 — Viewer + object insertion (core demo).**
- Web viewer that renders the Gaussian scene (correct orthographic projection) with free-viewpoint navigation.
- Load a GLB decoration, place it in the scene frame, transform it, and confirm it **stays anchored as the camera moves** (F4/F5).
- Simple "place on surface" using the scene's depth/geometry.
- **Exit criteria:** the CEO-demo loop works end-to-end: scan → near-live scene → drop a decoration → orbit and it stays put.

**Phase 3 — Track EDIT (static, perspective-correct, higher-quality).**
- Add `StaticGSReconstructor` (COLMAP + 3DGS, and/or NoPoSplat/AnySplat). Same capture, perspective + metric output.
- Use this scene for the polished/anchorable experience. Keep Track LIVE for the "watch it build" moment.
- **Exit criteria:** a higher-res, perspective-correct splat of the same closet, consumed through the same interface.

**Phase 4 — Scene editing (Stage 2 of the product).**
- Integrate Gaussian Grouping / GaussianEditor on the Track EDIT splat: recolor a surface, remove/replace an object.
- **Exit criteria:** recolor a wall and remove one real object in the scene.

**Phase 5 — Streaming + AR-ready.**
- Stream rendered view to the phone; prototype ARKit/ARCore anchoring of the decorated Track EDIT scene into the live room.
- **Exit criteria:** decorated scene displayed on phone, anchored to the real space; document what changes for glasses.

---

## 9. Open Decisions / Questions to resolve during build

1. **Live vs. quality for the demo:** ship Track LIVE only (Phase 2) for max "wow," or wait for Track EDIT (Phase 3) for better visuals? (Recommend: demo Track LIVE for the live magic + a pre-baked Track EDIT scene for the polished decorate moment.)
2. **Object source:** fixed asset library vs. image-to-3D generation. (Recommend: library first; generation as a stretch.)
3. **Placement frame:** confirm whether placing objects in StreamSplat's orthographic canonical space is "good enough" visually for v1, or whether Track EDIT is needed for believable placement. **Test early (Phase 2).**
4. **Licensing (blocking for commercial):** confirm StreamSplat repo license with authors; switch to Apache-licensed depth; verify no CC-BY-NC data in any retraining. Must be resolved before productization (see R4).
5. **Compute budget:** which GPU is available for the demo, and is inference run on-demand or pre-baked for the live session?

---

## 10. Reference Papers / Repos

- **StreamSplat** (engine) — arXiv:2506.08862 — https://github.com/DSL-Lab/StreamSplat
- **3D Gaussian Splatting** (foundation, Track EDIT) — Kerbl et al., SIGGRAPH 2023 — arXiv:2308.04079 — `graphdeco-inria/gaussian-splatting`
- **Depth Anything V2** (depth backbone) — Yang et al., NeurIPS 2024 — https://github.com/DepthAnything/Depth-Anything-V2
- **DINOv2** (features) — Oquab et al., 2023 — https://github.com/facebookresearch/dinov2
- **NoPoSplat / AnySplat / MVSplat** (static feed-forward alternatives, Track EDIT) — arXiv:2410.24207 / arXiv:2505.23716 / arXiv:2404.14627
- **Gaussian Grouping** (editing) — Ye et al., 2024 — arXiv:2312.00732
- **GaussianEditor** (editing) — Chen et al., CVPR 2024 — arXiv:2311.14521
- **Mobile-GS** (on-phone rendering, later) — real-time 3DGS rendering on mobile

---

## 11. Summary for the coding AI

Build a cloud-reconstruction + thin-client system that turns a phone video of a real space into a navigable 3D Gaussian scene and lets a user place virtual objects that stay anchored as the viewpoint moves. **Use StreamSplat as the primary reconstruction engine, wrapped behind a swappable `Reconstructor` interface.** Start by reproducing StreamSplat (Phase 0), then ingest real phone capture (Phase 1), then build the viewer + object insertion that is the core CEO demo (Phase 2). Treat StreamSplat's orthographic/dynamic/low-res/non-commercial-license characteristics as contained risks: keep a second static, perspective-correct reconstruction path (Phase 3) for editing (Phase 4) and AR anchoring (Phase 5). Do not couple the viewer, object insertion, editing, or AR layers to StreamSplat internals — they consume only the `GaussianScene` abstraction.
