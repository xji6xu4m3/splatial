from pathlib import Path
import cv2
import numpy as np


def resize_long_side(img: np.ndarray, long_side: int) -> np.ndarray:
    if not long_side or long_side <= 0:
        return img  # <=0 => keep native resolution (let the model's own resize downsample)
    h, w = img.shape[:2]
    scale = long_side / max(h, w)
    if scale >= 1.0:
        return img
    new_w, new_h = round(w * scale), round(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def pick_frame_indices(total: int, max_frames: int) -> list[int]:
    """Uniform temporal subsample (legacy / fallback when fps is unknown)."""
    if total <= max_frames:
        return list(range(total))
    if max_frames <= 1:
        return [0]
    step = (total - 1) / (max_frames - 1)
    return [round(i * step) for i in range(max_frames)]


# --- blur-aware fixed-rate sampling -------------------------------------------------
# Instead of a fixed view COUNT, target a fixed RATE (≈1 view/sec, like AnySplat's demo)
# so coverage scales with video length, bounded by [min_frames, max_frames] for VRAM.
# Within each time window we keep the SHARPEST frame (variance-of-Laplacian) to drop
# motion blur. Even windows over a steady sweep ⇒ roughly even angular spacing.

def variance_of_laplacian(img: np.ndarray) -> float:
    """Focus measure: higher = sharper. Variance of the Laplacian (Pech-Pacheco 2000)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def target_view_count(total_frames: int, fps: float, rate: float = 1.0,
                      min_frames: int = 8, max_frames: int = 16) -> int:
    """How many views to keep: ~`rate` per second, clamped to [min,max] and ≤ total."""
    if total_frames <= 0:
        return 0
    duration = total_frames / fps if fps and fps > 0 else 0.0
    n = round(duration * rate)
    n = max(min_frames, min(max_frames, n))
    return min(n, total_frames)


def window_bounds(total: int, n: int) -> list[tuple[int, int]]:
    """Partition [0, total) into `n` contiguous, non-overlapping windows [lo, hi)."""
    if n <= 0 or total <= 0:
        return []
    edges = [round(i * total / n) for i in range(n + 1)]
    return [(edges[i], edges[i + 1]) for i in range(n) if edges[i + 1] > edges[i]]


def select_sharpest_per_window(sharpness: list[float],
                               bounds: list[tuple[int, int]]) -> list[int]:
    """Pure: pick the highest-sharpness frame index within each window."""
    chosen: list[int] = []
    for lo, hi in bounds:
        if hi <= lo:
            continue
        seg = sharpness[lo:hi]
        chosen.append(lo + max(range(len(seg)), key=lambda k: seg[k]))
    return chosen


def extract_frames(video_path: str, out_dir: str, max_frames: int = 16,
                   long_side: int = 448, rate: float = 1.0, min_frames: int = 8,
                   blur_aware: bool = True) -> list[Path]:
    """Sample frames from a video and write resized PNGs to out_dir.

    Default (blur_aware): split the clip into ~`rate`/sec time windows (count clamped to
    [min_frames, max_frames]) and keep the SHARPEST frame per window — coverage scales with
    length, motion-blurred frames are dropped. Falls back to uniform sampling if fps/length
    is unavailable. `long_side<=0` keeps native resolution. Returns the written paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open video: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0

    if blur_aware and total > 0:
        n = target_view_count(total, fps, rate, min_frames, max_frames)
        bounds = window_bounds(total, n)
        # One pass: for each window keep the sharpest frame seen (store one image per window).
        best: dict[int, tuple[float, np.ndarray]] = {}
        i, w = 0, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            while w < len(bounds) - 1 and i >= bounds[w + 1][0]:
                w += 1
            if bounds and bounds[w][0] <= i < bounds[w][1]:
                s = variance_of_laplacian(frame)
                if w not in best or s > best[w][0]:
                    best[w] = (s, frame.copy())
            i += 1
        cap.release()
        written: list[Path] = []
        for w in sorted(best):
            img = resize_long_side(best[w][1], long_side)
            p = out / f"frame_{len(written):04d}.png"
            if not cv2.imwrite(str(p), img):
                raise RuntimeError(f"failed to write {p}")
            written.append(p)
        if not written:
            raise RuntimeError("no frames extracted")
        return written

    # Fallback: uniform index sampling (no blur metric).
    wanted = set(pick_frame_indices(total, max_frames)) if total else set()
    written = []
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
