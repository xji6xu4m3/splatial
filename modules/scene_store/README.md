# scene_store

Shared data contracts and folder-based persistence for Splatial scenes.

## Public API

### `contracts.py`

Three dataclasses that are serialised to / deserialised from JSON and form the
only coupling between the Python pipeline and the web viewer.

```python
Transform(position: list[float], rotation: list[float], scale: list[float])
# rotation is a quaternion [x, y, z, w]

SplatScene(id: str, ply: str, bbox: list[list[float]], up: list[float],
           scale_hint: float, source_meta: dict = {})

SceneObject(id: str, glb: str, transform: Transform,
            material_overrides: dict, scene_id: str)
```

Each dataclass exposes `.to_dict() -> dict` and a static `.from_dict(d: dict)`.

### `store.py`

```python
scene_dir(root, scene_id: str) -> Path
    # Returns (and creates) Path(root) / scene_id

save_scene(root, scene: SplatScene) -> Path
    # Writes scenes/<id>/scene.json

load_scene(root, scene_id: str) -> SplatScene
    # Reads scenes/<id>/scene.json

save_objects(root, scene_id: str, objects: list[SceneObject]) -> Path
    # Writes scenes/<id>/objects.json

load_objects(root, scene_id: str) -> list[SceneObject]
    # Reads scenes/<id>/objects.json; returns [] if file absent
```

## Scene folder layout

```
scenes/<id>/
  scene.ply       # 3DGS point cloud (INRIA format)
  scene.json      # SplatScene  (see data contract below)
  objects.json    # list[SceneObject]
```

## Shared data contracts (JSON shape)

```json
// scene.json  — SplatScene
{
  "id": "room1",
  "ply": "scene.ply",
  "bbox": [[-1.0, -0.5, -1.0], [1.0, 2.0, 1.0]],
  "up": [0.0, 1.0, 0.0],
  "scale_hint": 1.0,
  "source_meta": { "model": "anysplat", "n_views": 16, "n_gaussians": 80000 }
}

// objects.json  — list[SceneObject]
[
  {
    "id": "o1",
    "glb": "assets/chair.glb",
    "transform": {
      "position": [0.0, 0.0, 0.0],
      "rotation": [0.0, 0.0, 0.0, 1.0],
      "scale": [1.0, 1.0, 1.0]
    },
    "material_overrides": { "color": [1.0, 0.0, 0.0] },
    "scene_id": "room1"
  }
]
```
