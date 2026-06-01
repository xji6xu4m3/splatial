# Splatial

Scan a real space with a phone camera, reconstruct it as an editable **3D Gaussian Splatting** scene, and place / edit virtual furniture that stays anchored as the viewpoint moves. **Camera-only** (no LiDAR), splat-based, built modular so each piece can scale or be swapped independently. End target: AR/AI glasses (Meta lineage); the phone is the interim capture device.

- **Design spec:** [`docs/superpowers/specs/2026-06-01-ar-scan-edit-design.md`](docs/superpowers/specs/2026-06-01-ar-scan-edit-design.md)
- **Reconstruction engine:** AnySplat (MIT) — feed-forward 3DGS from uncalibrated phone video.
- **Status:** Design phase. POC demo target: a small room + a placed, editable piece of furniture.

## Repository layout (planned)

```
docs/            Design specs, per-module API docs
modules/
  capture/       Phone video -> frames
  reconstruct/   Frames -> SplatScene (.ply + metadata)   [AnySplat]
  scene_store/   Persist splats, placed objects, edit ops
  viewer/        Render splat + objects (free-viewpoint)
  objects/       Place / transform / edit GLB furniture in the splat frame
assets/          GLB furniture library
```

Each module owns a README documenting its data contract and public API.
