from pathlib import Path
import cv2
import numpy as np


def resize_long_side(img: np.ndarray, long_side: int) -> np.ndarray:
    h, w = img.shape[:2]
    scale = long_side / max(h, w)
    if scale >= 1.0:
        return img
    new_w, new_h = round(w * scale), round(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def pick_frame_indices(total: int, max_frames: int) -> list[int]:
    if total <= max_frames:
        return list(range(total))
    if max_frames <= 1:
        return [0]
    step = (total - 1) / (max_frames - 1)
    return [round(i * step) for i in range(max_frames)]


def extract_frames(video_path: str, out_dir: str, max_frames: int = 16,
                   long_side: int = 448) -> list[Path]:
    """Sample up to `max_frames` uniformly-spaced frames from a video, resize so the
    longest side <= `long_side`, write PNGs to out_dir. Returns the written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    wanted = set(pick_frame_indices(total, max_frames)) if total else set()
    written: list[Path] = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if not wanted or i in wanted:
            frame = resize_long_side(frame, long_side)
            p = out / f"frame_{len(written):04d}.png"
            if not cv2.imwrite(str(p), frame):
                raise RuntimeError(f"failed to write {p}")
            written.append(p)
        i += 1
    cap.release()
    if not written:
        raise RuntimeError("no frames extracted")
    return written
