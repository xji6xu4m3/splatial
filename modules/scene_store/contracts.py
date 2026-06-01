from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class Transform:
    position: list[float]
    rotation: list[float]   # quaternion [x, y, z, w]
    scale: list[float]

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Transform":
        return Transform(position=list(d["position"]),
                         rotation=list(d["rotation"]),
                         scale=list(d["scale"]))


@dataclass
class SplatScene:
    id: str
    ply: str
    bbox: list[list[float]]
    up: list[float]
    scale_hint: float
    source_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SplatScene":
        return SplatScene(id=d["id"], ply=d["ply"], bbox=d["bbox"],
                          up=d["up"], scale_hint=d["scale_hint"],
                          source_meta=d.get("source_meta", {}))


@dataclass
class SceneObject:
    id: str
    glb: str
    transform: Transform
    material_overrides: dict
    scene_id: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SceneObject":
        return SceneObject(id=d["id"], glb=d["glb"],
                           transform=Transform.from_dict(d["transform"]),
                           material_overrides=d.get("material_overrides", {}),
                           scene_id=d["scene_id"])
