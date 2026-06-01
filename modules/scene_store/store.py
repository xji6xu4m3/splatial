import json
from pathlib import Path
from .contracts import SplatScene, SceneObject


def _scene_path(root, scene_id: str) -> Path:
    """Return the scene directory path without creating it (safe for reads)."""
    root = Path(root).resolve()
    d = (root / scene_id).resolve()
    if not str(d).startswith(str(root) + "/") and d != root:
        raise ValueError(f"scene_id escapes root: {scene_id!r}")
    return d


def scene_dir(root, scene_id: str) -> Path:
    """Return the scene directory, creating it if necessary (for writes)."""
    d = _scene_path(root, scene_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_scene(root, scene: SplatScene) -> Path:
    d = scene_dir(root, scene.id)
    p = d / "scene.json"
    p.write_text(json.dumps(scene.to_dict(), indent=2))
    return p


def load_scene(root, scene_id: str) -> SplatScene:
    p = _scene_path(root, scene_id) / "scene.json"
    return SplatScene.from_dict(json.loads(p.read_text()))


def save_objects(root, scene_id: str, objects: list[SceneObject]) -> Path:
    p = scene_dir(root, scene_id) / "objects.json"
    p.write_text(json.dumps([o.to_dict() for o in objects], indent=2))
    return p


def load_objects(root, scene_id: str) -> list[SceneObject]:
    p = _scene_path(root, scene_id) / "objects.json"
    if not p.exists():
        return []
    return [SceneObject.from_dict(x) for x in json.loads(p.read_text())]
