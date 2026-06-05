"""Pick a default reconstruction view cap that matches the host GPU's VRAM.

Bigger card -> more input views fit -> denser scan. The design-spec tiers are nominal
(12 / 16-24 / 40 GB), but `torch.cuda.get_device_properties().total_memory` reports a bit
UNDER nominal (driver reserve): a 16 GB card reads ~15.6 GB, a 40 GB A100 ~39.5 GB. So the
cut points sit below the nominal numbers (14 and 34 GB of headroom) to classify real cards
correctly: 12 GB -> 16, 16/24 GB -> 32, 40/80 GB -> 48. Override via MAX_VIEWS downstream.
"""

GB = 1024 ** 3


def default_max_views(total_vram_bytes: int | None) -> int:
    if not total_vram_bytes or total_vram_bytes <= 0:
        return 16
    gb = total_vram_bytes / GB
    if gb < 14:          # 12 GB cards report ~11.7 GB
        return 16
    if gb < 34:          # 16/24 GB cards report ~15.6 / ~23.6 GB
        return 32
    return 48            # 40/80 GB report ~39.5 / ~79.3 GB
