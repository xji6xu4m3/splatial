"""Pick a default reconstruction view cap that matches the host GPU's VRAM.

Bigger card -> more input views fit -> denser scan. Thresholds mirror the design spec:
<16GB -> 16, <40GB -> 32, else 48. Overridable via the MAX_VIEWS env var downstream.
"""

GB = 1024 ** 3


def default_max_views(total_vram_bytes: int | None) -> int:
    if not total_vram_bytes or total_vram_bytes <= 0:
        return 16
    gb = total_vram_bytes / GB
    if gb < 16:
        return 16
    if gb < 40:
        return 32
    return 48
