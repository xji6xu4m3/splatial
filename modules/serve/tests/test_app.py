import io
import json
from pathlib import Path

import pytest

from modules.serve.app import create_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    # isolate scenes/ data/ to a temp dir; record recon launches instead of running torch
    launched = []

    def fake_launcher(video, scene, scenes_root, status):
        launched.append((video, scene))
        d = Path(scenes_root) / scene
        d.mkdir(parents=True, exist_ok=True)
        (d / "scene.json").write_text(json.dumps({"id": scene, "ply": "scene.ply", "up": [0, 1, 0]}))
        status[scene] = "done"

    app = create_app(
        scenes_root=tmp_path / "scenes",
        data_root=tmp_path / "data",
        viewer_dist=tmp_path / "dist",
        assets_root=tmp_path / "assets",
        recon_launcher=fake_launcher,
    )
    # a minimal built viewer + a scene to serve
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<!doctype html><title>viewer</title>")
    app.config["LAUNCHED"] = launched
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_is_capture_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"capture" in r.data.lower()


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200 and r.get_json()["ok"] is True


def test_view_serves_viewer_build(client):
    r = client.get("/view")
    assert r.status_code == 200 and b"viewer" in r.data.lower()


def test_coop_coep_headers_present(client):
    r = client.get("/view")
    assert r.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert r.headers["Cross-Origin-Embedder-Policy"] == "credentialless"


def test_upload_enqueues_and_serves_scene(client, app):
    data = {"scene": "room9", "video": (io.BytesIO(b"fakevideo"), "room9.mp4")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert app.config["LAUNCHED"] == [(str(Path(app.config["DATA"]) / "room9.mp4"), "room9")]
    # scene.json now served same-origin
    sj = client.get("/scenes/room9/scene.json")
    assert sj.status_code == 200 and sj.get_json()["id"] == "room9"


def test_upload_rejects_bad_scene_name(client):
    data = {"scene": "Bad Name!", "video": (io.BytesIO(b"x"), "x.mp4")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_result_page_links_to_same_origin_view(client):
    data = {"scene": "room8", "video": (io.BytesIO(b"x"), "room8.mp4")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert b"/view?scene=room8" in r.data


def test_status_unknown_then_done(client):
    assert client.get("/status/nope").get_json()["state"] == "unknown"
    client.post("/upload", data={"scene": "room7", "video": (io.BytesIO(b"x"), "room7.mp4")},
                content_type="multipart/form-data")
    # the fake launcher completes synchronously
    assert client.get("/status/room7").get_json()["state"] == "done"


def test_up_updates_scene_json(client):
    client.post("/upload", data={"scene": "room6", "video": (io.BytesIO(b"x"), "room6.mp4")},
                content_type="multipart/form-data")
    r = client.post("/up/room6", json={"up": [0, 0, 1]})
    assert r.status_code == 200 and r.get_json()["up"] == [0.0, 0.0, 1.0]
    assert client.get("/scenes/room6/scene.json").get_json()["up"] == [0.0, 0.0, 1.0]


def test_up_rejects_bad_body(client):
    client.post("/upload", data={"scene": "room5", "video": (io.BytesIO(b"x"), "room5.mp4")},
                content_type="multipart/form-data")
    assert client.post("/up/room5", json={"up": [1, 2]}).status_code == 400


def test_up_404_for_missing_scene(client):
    assert client.post("/up/ghost", json={"up": [0, 1, 0]}).status_code == 404


def test_delete_moves_scene_to_trash(client, app):
    client.post("/upload", data={"scene": "room4", "video": (io.BytesIO(b"x"), "room4.mp4")},
                content_type="multipart/form-data")
    scenes_root = Path(app.config["SCENES"])
    assert (scenes_root / "room4").is_dir()
    r = client.post("/delete/room4")
    assert r.status_code == 200 and r.get_json()["deleted"] == "room4"
    assert not (scenes_root / "room4").exists()
    assert (scenes_root / ".trash" / "room4").is_dir()


def test_upload_over_size_limit_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "16")  # tiny cap
    app = create_app(scenes_root=tmp_path / "s", data_root=tmp_path / "d",
                     viewer_dist=tmp_path / "v", assets_root=tmp_path / "a",
                     recon_launcher=lambda *a: None)
    r = app.test_client().post(
        "/upload",
        data={"scene": "big", "video": (io.BytesIO(b"x" * 1000), "big.mp4")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 413
