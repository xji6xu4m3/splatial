# Splatial

Scan a real space with a phone camera, reconstruct it as an editable **3D Gaussian Splatting** scene, and place / edit virtual furniture that stays anchored as the viewpoint moves. **Camera-only** (no LiDAR), splat-based, built modular so each piece can scale or be swapped independently. End target: AR/AI glasses (Meta lineage); the phone is the interim capture device.

- **Design spec:** [`docs/superpowers/specs/2026-06-01-ar-scan-edit-design.md`](docs/superpowers/specs/2026-06-01-ar-scan-edit-design.md)
- **Reconstruction:** AnySplat (MIT) — feed-forward 3DGS from uncalibrated phone video.
- **Objects:** pre-built GLB library **+ live voice→3D generation** ("create a 3D chair!" → SDXL-Turbo → TRELLIS → GLB).
- **Editing:** virtual objects (recolor/swap/move) **and** the real scene (recolor wall / remove object, pre-baked).
- **Viewer:** web / Three.js, free-viewpoint orbit.
- **Status:** Design phase. POC target: a small room, placed + generated + editable objects, real-scene edits.

## Repository layout (planned)

```
docs/            Design specs, per-module API docs
modules/
  capture/       Phone video -> frames
  reconstruct/   Frames -> SplatScene (.ply + metadata)   [AnySplat]
  scene_store/   Persist splats, placed objects, edit ops
  generate/      Voice/text -> GLB  [Web Speech API -> SDXL-Turbo -> TRELLIS] + pre-gen cache
  objects/       Acquire (library | generated) + place/transform GLB in the splat frame
  editor/        Edit ops: objects + real-scene splat variants
  viewer/        Render splat + objects (free-viewpoint, mic button)
assets/          Pre-built GLB library + pre-generated cache
```

Each module owns a README documenting its data contract and public API.
