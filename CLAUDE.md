# Splatial — Project Guide

Scan a small room with a phone camera (camera-only, no LiDAR), reconstruct it as an editable 3D Gaussian Splatting (3DGS) scene with AnySplat, view it in a web/Three.js free-viewpoint viewer, and populate it with pre-built and voice-generated GLB objects that stay anchored as the camera orbits. Objects and the real scene are both editable (move/rotate/scale/recolor/swap; recolor a wall, remove a real object). The reconstruction is the canvas; **believable placement, generation, and editing are the wow.** Phone is the interim capture device; the end product is Meta AR/AI glasses (Quest 3 → Orion). The demo is deterministic — every "live" moment has a pre-baked artifact behind it.

## Confirmed constraints
- **Camera-only** — reconstruction from RGB phone video only, no LiDAR/ARKit.
- **Splat-based** — 3DGS is the scene representation (not mesh).
- **Editing is the wow** — believable anchored placement + object/scene editing; live-reconstruction speed is not the priority.
- **< 2 weeks to demo** — de-risked, off-the-shelf components; tiered [CORE] vs [WOW] phases.
- **Commercial path** — prefer MIT/Apache models; flag every non-commercial dependency.
- **Meta glasses end goal** — phone + web viewer are interim; architected to port to OpenXR later.

## Architecture
Python pipeline (`capture` → `reconstruct`) writes a scene folder; web viewer renders it. Modules talk **only** through shared data contracts — never reach into each other's internals (each module owns a README documenting its public API).

```
capture ──frames──▶ reconstruct ──SplatScene──▶ scene_store ◀──persist── objects/editor/generate
                                       └────────────── viewer ◀──────────────┘
                                           (renders SplatScene + SceneObjects)
```

### 7 modules
- **capture** — phone video → ordered frames (uniform sampling, resize). `extract_frames(video) -> [Frame]`. Pure logic → TDD.
- **reconstruct** — frames → `SplatScene` (+ `scene.ply`) behind one `Reconstructor` interface (AnySplat primary, VGGT+gsplat fallback), selected by `make_reconstructor(engine)` / `RECON_ENGINE`. `reconstruct(image_paths, scene_id, out_ply) -> SplatScene`. Run-and-verify (ML).
- **scene_store** — persist/load splats, objects, edit ops on a scene folder. `save_scene`/`load_scene`/`save_objects`/`load_objects`/`apply(EditOp)`. Pure logic → TDD.
- **generate** — voice/text → GLB (Web Speech API → SDXL-Turbo → TRELLIS) with a pre-generated keyword cache; live fallback ~30–40s. `from_text(prompt) -> glb`.
- **objects** — acquire a GLB via one of two `ObjectProvider`s (`LibraryObjectProvider`, `GeneratedObjectProvider`), place/surface-snap it in the splat frame. `get(query) -> glb`, `place(glb, transform) -> SceneObject`.
- **editor** — apply `EditOp`s to objects (transform/recolor/swap) and to the real scene (recolor/remove via pre-baked splat variants); same API a live editor would use. `apply(EditOp) -> SplatScene|SceneObject`.
- **viewer** — web/Three.js (`@mkkellogg/gaussian-splats-3d`), free-viewpoint orbit, mic button; renders from `scene_store`.

### Shared data contracts
A scene folder is the unit of exchange: `scenes/<id>/{scene.ply, scene.json, objects.json}`. Contracts are authored once in `modules/scene_store/contracts.py` and mirrored in JSON the viewer reads.
```
SplatScene  { id, ply, bbox[[min],[max]], up[x,y,z], scale_hint, source_meta }
SceneObject { id, glb, transform, material_overrides{color?}, scene_id }
Transform   { position[x,y,z], rotation[x,y,z,w], scale[x,y,z] }   # rotation = quaternion, order [x,y,z,w]
EditOp      { id, target(object_id|scene), kind(transform|recolor|swap|remove), params }
```
Anchoring is automatic: objects live in the splat's coordinate frame, so they stay put as the camera orbits — no SLAM needed for the POC.

## Reconstruction engines
- **Primary: AnySplat** (`lhjiang/anysplat`, MIT) — uncalibrated/unposed RGB → standard perspective 3DGS in one pass. Up-to-scale (not metric), batch (not streaming), static model. Verify VGGT-distillation provenance before commercial ship.
- **Fallback: VGGT-1B-Commercial → gsplat** (commercial-gated / Apache-2.0) — if AnySplat quality or VRAM disappoints.
- Both sit behind **one `Reconstructor` interface**; select via a `RECON_ENGINE` switch (default `anysplat`). The adapter never leaks backend internals.
- Optional per-scene sharpening: gsplat post-opt (1–3k steps) on the hero scene.

## How to run
```bash
# Python (from repo root)
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                                              # capture + scene_store + reconstruct smoke

# Reconstruct a room: video → scene folder
python -m modules.reconstruct.cli <video> scenes <id>   # e.g. data/room1.mp4 scenes room1

# Web viewer
cd web && npm install && npm run dev                # http://localhost:5173/?scene=<id>
cd web && npx playwright test                       # viewer smoke test
```
Test camera is available at `/dev/video0` (the phone camera is the real capture device in the end product). Scene folders and `web/scenes`, `web/assets` symlinks are gitignored.

## Deterministic demo strategy
Everything shown is pre-baked so nothing stalls in front of the CEO: pre-reconstructed scene `.ply`s, a pre-generated GLB cache keyed by recognized word (instant placement), and pre-baked real-scene edit variants (wall recolored, object removed+inpainted) the viewer toggles. The genuinely-live pipeline (live generation, live editing) runs **behind the cache** and for post-demo use — the `editor`/`generate` APIs are identical for cached and live paths, so going live is a swap, not a rewrite. If a [WOW] item slips, the [CORE] demo still stands.

## GPU reality
Demo GPU = **RTX 4070 Ti (12 GB)** — tight for feed-forward recon. Mitigations:
- Cap input **views ~8–24** and **resolution ≤448px** long side (drop to 8 views / 384px if it OOMs).
- Set `ATTN_BACKEND=xformers`, `SPCONV_ALGO=native`; `torch.cuda.empty_cache()` after inference; load/unload SDXL↔TRELLIS sequentially.
- **Cloud GPU fallback** (A10/L4/A100, same CLI command) documented from day 1 for larger scans.
- TRELLIS.2-4B (needs 24GB) and Hunyuan3D-2.1 (restrictive license + >12GB texture stage) are **out** — won't fit / not commercial-safe.

## Conventions
- **Commits**: conventional commits — `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `perf:`, `ci:` (scope optional, e.g. `feat(capture):`). Attribution disabled globally.
- **Per-module README**: every module documents its public API + data contract in its own `README.md`.
- **Testing**: TDD where logic is pure (`capture`, `scene_store`, transforms) — write the failing test first. Run-and-verify for ML (`reconstruct`, `generate`) and web (`viewer`) — mock the model in unit smoke tests, confirm real output by running the pipeline / Playwright.
- **License hygiene**: prefer MIT/Apache; flag any non-commercial dependency (blocking for product, not demo).

## Ground-truth docs
- Design spec: `/home/liylo/Desktop/AR/docs/superpowers/specs/2026-06-01-ar-scan-edit-design.md`
- Foundation plan (Phase 0 + Phase 1, file structure, task-by-task TDD): `/home/liylo/Desktop/AR/docs/superpowers/plans/2026-06-01-splatial-foundation.md`

Do not contradict the spec or plan — they are ground truth.
