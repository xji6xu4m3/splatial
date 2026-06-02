import numpy as np
import cv2
from pathlib import Path
from modules.capture.frames import (
    resize_long_side, pick_frame_indices,
    variance_of_laplacian, target_view_count, window_bounds,
    select_sharpest_per_window,
)


def test_resize_long_side_caps_longest_dimension():
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)  # H, W
    out = resize_long_side(img, 448)
    h, w = out.shape[:2]
    assert max(h, w) == 448
    assert abs((w / h) - (1920 / 1080)) < 0.02  # aspect preserved


def test_resize_long_side_native_when_nonpositive():
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert resize_long_side(img, 0).shape == img.shape   # 0 => keep native


def test_pick_frame_indices_uniform_and_capped():
    idx = pick_frame_indices(total=100, max_frames=8)
    assert len(idx) == 8
    assert idx[0] == 0 and idx[-1] == 99
    assert idx == sorted(idx) and len(set(idx)) == 8


def test_pick_frame_indices_fewer_than_max():
    idx = pick_frame_indices(total=5, max_frames=8)
    assert idx == [0, 1, 2, 3, 4]


# --- blur-aware fixed-rate sampling -------------------------------------------------

def test_variance_of_laplacian_sharper_scores_higher():
    blurry = np.full((64, 64, 3), 127, dtype=np.uint8)            # flat = no edges
    sharp = np.indices((64, 64)).sum(0).astype(np.uint8)         # gradient/edges
    sharp = cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)
    assert variance_of_laplacian(sharp) > variance_of_laplacian(blurry)


def test_target_view_count_scales_with_length_and_clamps():
    # ~1 view/sec at the default rate, clamped to [min, max]
    assert target_view_count(total_frames=450, fps=30, rate=1.0, min_frames=8, max_frames=16) == 15  # 15s
    assert target_view_count(total_frames=1800, fps=30, rate=1.0, min_frames=8, max_frames=16) == 16  # 60s -> capped
    assert target_view_count(total_frames=60, fps=30, rate=1.0, min_frames=8, max_frames=16) == 8     # 2s -> floored
    assert target_view_count(total_frames=5, fps=30, rate=1.0, min_frames=8, max_frames=16) == 5       # never exceed frames


def test_window_bounds_partitions_contiguously():
    b = window_bounds(total=30, n=8)
    assert len(b) == 8
    assert b[0][0] == 0 and b[-1][1] == 30
    for (lo, hi), (nlo, _) in zip(b, b[1:]):
        assert hi == nlo and hi > lo            # contiguous, non-empty, no gaps/overlap


def test_select_sharpest_per_window_picks_local_max():
    # sharpness per frame index; one peak per window
    sharp = [0.1, 0.9, 0.2,  0.3, 0.1, 0.8,  0.7, 0.2, 0.1]
    bounds = [(0, 3), (3, 6), (6, 9)]
    assert select_sharpest_per_window(sharp, bounds) == [1, 5, 6]


def test_extract_frames_picks_sharp_frame_in_each_window(tmp_path):
    vid = tmp_path / "clip.mp4"
    vw = cv2.VideoWriter(str(vid), cv2.VideoWriter_fourcc(*"mp4v"), 4.0, (64, 64))
    # 16 frames @ 4fps = 4s. Every 4th frame is a sharp checkerboard; the rest are flat.
    flat = np.full((64, 64, 3), 127, dtype=np.uint8)
    checker = (np.indices((64, 64)).sum(0) % 2 * 255).astype(np.uint8)
    checker = cv2.cvtColor(checker, cv2.COLOR_GRAY2BGR)
    for k in range(16):
        vw.write(checker if k % 4 == 2 else flat)
    vw.release()

    from modules.capture.frames import extract_frames
    paths = extract_frames(str(vid), str(tmp_path / "frames"), max_frames=16,
                           long_side=0, rate=1.0, min_frames=4)
    assert len(paths) == 4                      # 4s @ ~1fps
    # every chosen frame should be the sharp checkerboard (high Laplacian variance)
    for p in paths:
        assert variance_of_laplacian(cv2.imread(str(p))) > 100
