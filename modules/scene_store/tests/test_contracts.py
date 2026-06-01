from modules.scene_store.contracts import SplatScene, SceneObject, Transform


def test_transform_roundtrip():
    t = Transform(position=[1, 2, 3], rotation=[0, 0, 0, 1], scale=[1, 1, 1])
    assert Transform.from_dict(t.to_dict()) == t


def test_splatscene_roundtrip():
    s = SplatScene(id="room1", ply="scene.ply",
                   bbox=[[0, 0, 0], [1, 1, 1]], up=[0, 1, 0],
                   scale_hint=1.0, source_meta={"frames": 16})
    assert SplatScene.from_dict(s.to_dict()) == s


def test_sceneobject_roundtrip():
    o = SceneObject(id="o1", glb="assets/chair.glb",
                    transform=Transform([0, 0, 0], [0, 0, 0, 1], [1, 1, 1]),
                    material_overrides={"color": [1.0, 0.0, 0.0]}, scene_id="room1")
    assert SceneObject.from_dict(o.to_dict()) == o
