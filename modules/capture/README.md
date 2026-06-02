# capture

Selects the best frames from a phone video (blur-aware, fixed-rate) and resizes them for the
reconstruction pipeline.

## Sampling strategy

Rather than a fixed view **count**, we target a fixed **rate** (≈1 view/sec, like AnySplat's
demo) so coverage scales with clip length, bounded to `[min_frames, max_frames]` for VRAM. The
clip is split into that many equal time **windows**, and within each window we keep the
**sharpest** frame (variance-of-Laplacian) to drop motion blur. Even windows over a steady sweep
give roughly even angular spacing. (True motion/speed-awareness would use optical flow — a
future refinement.)

## Public API

### `resize_long_side(img, long_side) -> np.ndarray`
Resize a BGR image so its longest dimension equals `long_side` (downscale only, `INTER_AREA`).
`long_side <= 0` keeps native resolution (the model resizes internally).

### `variance_of_laplacian(img) -> float`
Focus measure (higher = sharper) used to pick the least-blurred frame per window.

### `target_view_count(total_frames, fps, rate=1.0, min_frames=8, max_frames=16) -> int`
How many views to keep: `clamp(round(duration*rate), min, max)`, never exceeding `total_frames`.

### `window_bounds(total, n) -> list[(lo, hi)]`
Partition `[0, total)` into `n` contiguous, non-overlapping windows.

### `select_sharpest_per_window(sharpness, bounds) -> list[int]`
Pure: the highest-sharpness frame index within each window.

### `extract_frames(video_path, out_dir, max_frames=16, long_side=448, rate=1.0, min_frames=8, blur_aware=True) -> list[Path]`
Sample frames and write `frame_NNNN.png` to `out_dir`. Default = blur-aware fixed-rate (above);
`blur_aware=False` falls back to uniform `pick_frame_indices`. Raises `FileNotFoundError` if the
video can't be opened, `RuntimeError` if nothing was extracted.

### `pick_frame_indices(total, max_frames) -> list[int]`
Uniform temporal subsample (legacy / fallback when fps is unknown).

Tuned at the CLI via env: `MAX_VIEWS` (default 16), `MIN_VIEWS` (8), `CAPTURE_RATE` (1.0 /sec),
`CAPTURE_LONG_SIDE` (0 = native).

## Data contracts

This module produces PNG files consumed by the `reconstruct` module's `AnySplatReconstructor.reconstruct(image_paths, ...)`. The `image_paths` argument is the `list[Path]` returned by `extract_frames`.

No JSON contracts are defined here — frames are filesystem artefacts only.
