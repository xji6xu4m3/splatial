# capture

Extracts uniformly-spaced frames from a phone video and resizes them for the reconstruction pipeline.

## Public API

### `resize_long_side(img: np.ndarray, long_side: int) -> np.ndarray`

Resizes a BGR image so its longest dimension equals `long_side`. Returns the image unchanged if it is already smaller. Uses `cv2.INTER_AREA` (good for downscaling).

### `pick_frame_indices(total: int, max_frames: int) -> list[int]`

Returns a list of at most `max_frames` frame indices, uniformly distributed from 0 to `total-1` inclusive. If `total <= max_frames`, returns `list(range(total))`. If `max_frames <= 1`, returns `[0]` (only the first frame).

### `extract_frames(video_path, out_dir, max_frames=16, long_side=448) -> list[Path]`

Opens a video file, samples up to `max_frames` frames uniformly, resizes each so its longest side is `<= long_side`, and writes them as `frame_NNNN.png` into `out_dir` (created if absent). Returns the list of written `Path` objects.

Raises `FileNotFoundError` if the video cannot be opened, and `RuntimeError` if no frames were extracted.

## Data contracts

This module produces PNG files consumed by the `reconstruct` module's `AnySplatReconstructor.reconstruct(image_paths, ...)`. The `image_paths` argument is the `list[Path]` returned by `extract_frames`.

No JSON contracts are defined here — frames are filesystem artefacts only.
