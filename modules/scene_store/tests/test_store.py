from modules.scene_store.contracts import SplatScene, SceneObject, Transform
from modules.scene_store.store import scene_dir, save_scene, load_scene, save_objects, load_objects


def test_save_and_load_scene(tmp_path):
    s = SplatScene(id="room1", ply="scene.ply", bbox=[[0, 0, 0], [1, 1, 1]],
                   up=[0, 1, 0], scale_hint=1.0, source_meta={})
    save_scene(tmp_path, s)
    assert (scene_dir(tmp_path, "room1") / "scene.json").exists()
    assert load_scene(tmp_path, "room1") == s


def test_save_and_load_objects(tmp_path):
    s = SplatScene(id="room1", ply="scene.ply", bbox=[[0, 0, 0], [1, 1, 1]],
                   up=[0, 1, 0], scale_hint=1.0, source_meta={})
    save_scene(tmp_path, s)
    objs = [SceneObject("o1", "assets/chair.glb",
                        Transform([0, 0, 0], [0, 0, 0, 1], [1, 1, 1]), {}, "room1")]
    save_objects(tmp_path, "room1", objs)
    assert load_objects(tmp_path, "room1") == objs
