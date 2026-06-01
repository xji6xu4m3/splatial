import numpy as np
import cv2
from pathlib import Path
from modules.capture.frames import resize_long_side, pick_frame_indices


def test_resize_long_side_caps_longest_dimension():
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)  # H, W
    out = resize_long_side(img, 448)
    h, w = out.shape[:2]
    assert max(h, w) == 448
    assert abs((w / h) - (1920 / 1080)) < 0.02  # aspect preserved


def test_pick_frame_indices_uniform_and_capped():
    idx = pick_frame_indices(total=100, max_frames=8)
    assert len(idx) == 8
    assert idx[0] == 0 and idx[-1] == 99
    assert idx == sorted(idx) and len(set(idx)) == 8


def test_pick_frame_indices_fewer_than_max():
    idx = pick_frame_indices(total=5, max_frames=8)
    assert idx == [0, 1, 2, 3, 4]


def test_extract_frames_writes_capped_resized_pngs(tmp_path):
    vid = tmp_path / "clip.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(str(vid), fourcc, 10.0, (640, 480))
    for k in range(30):
        vw.write(np.full((480, 640, 3), k * 5 % 255, dtype=np.uint8))
    vw.release()

    from modules.capture.frames import extract_frames
    paths = extract_frames(str(vid), str(tmp_path / "frames"), max_frames=8, long_side=320)
    assert len(paths) == 8
    img = cv2.imread(str(paths[0]))
    assert max(img.shape[:2]) == 320
