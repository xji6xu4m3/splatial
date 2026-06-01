import numpy as np
from pathlib import Path
from modules.reconstruct.anysplat_provider import AnySplatReconstructor
from modules.reconstruct.vggt_provider import VGGTReconstructor
from modules.reconstruct.factory import make_reconstructor


class _FakeGaussians:
    _means_data = np.random.rand(100, 3)
    means = type("M", (), {"detach": lambda self: self,
                            "cpu": lambda self: self,
                            "numpy": lambda self, d=_means_data: d})()

    def save_ply(self, p):
        Path(p).write_text("ply\nfake\n")


def test_reconstruct_builds_scene(tmp_path, monkeypatch):
    # Hermetic: stub the three AnySplat-touching methods so no torch/AnySplat is needed.
    r = AnySplatReconstructor()
    monkeypatch.setattr(r, "_run_anysplat", lambda paths: ("G", None))
    monkeypatch.setattr(r, "_export_ply", lambda g, out: Path(out).write_text("ply\nfake\n"))
    monkeypatch.setattr(r, "_gaussian_xyz", lambda g: np.random.rand(100, 3))
    out = tmp_path / "scene.ply"
    scene = r.reconstruct([Path("a.png"), Path("b.png")], "room1", out)
    assert out.exists()
    assert scene.id == "room1"
    assert scene.source_meta["n_gaussians"] == 100
    assert scene.source_meta["n_views"] == 2
    assert len(scene.bbox) == 2 and len(scene.bbox[0]) == 3


def test_vggt_reconstruct_builds_scene(tmp_path, monkeypatch):
    r = VGGTReconstructor()
    fake_gaussians = _FakeGaussians()
    monkeypatch.setattr(r, "_run_vggt", lambda paths: {"poses": None, "depth": None, "pointmaps": None})
    def _fake_optimize(vggt_out, out_ply):
        Path(out_ply).write_text("ply\nfake\n")
        return fake_gaussians
    monkeypatch.setattr(r, "_optimize_gsplat", _fake_optimize)
    out = tmp_path / "scene.ply"
    scene = r.reconstruct([Path("a.png"), Path("b.png")], "room2", out)
    assert out.exists()
    assert scene.id == "room2"
    assert scene.source_meta["model"] == "vggt+gsplat"
    assert scene.source_meta["n_gaussians"] == 100
    assert len(scene.bbox) == 2 and len(scene.bbox[0]) == 3


def test_factory_returns_anysplat():
    r = make_reconstructor("anysplat")
    assert isinstance(r, AnySplatReconstructor)


def test_factory_returns_vggt():
    r = make_reconstructor("vggt")
    assert isinstance(r, VGGTReconstructor)


def test_factory_unknown_engine_raises():
    try:
        make_reconstructor("unknown_engine")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "unknown_engine" in str(e)
