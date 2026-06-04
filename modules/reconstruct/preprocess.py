"""License-clean image preprocessing for AnySplat inference.

Replaces `external_AnySplat/src/utils/image.py:process_image` (which is CC-BY-NC-SA 4.0,
non-commercial — the only non-commercial code path in reconstruct) with an MIT-compatible
re-implementation, AND recovers vertical field-of-view that the original threw away.

The original resizes the SHORT side to 448 and HARD center-crops to 448×448 square. For a
1080×1920 portrait phone frame that discards ~57% of the vertical extent (448 of 796 kept) —
starving room reconstructions of surface coverage. AnySplat's ViT backbone (patch=14) accepts
any H,W divisible by 14, so we keep the short side at 448 and crop the LONG side to a larger
cap (rounded down to a multiple of 14). `long_cap=448` reproduces the original square crop.

Returns a CHW float tensor in [-1, 1], RGB — identical convention to the original.
"""
from PIL import Image, ImageOps
import torchvision


def _round14(x: int) -> int:
    """Largest multiple of 14 that is <= x (ViT patch size), min one patch."""
    return max(14, x - (x % 14))


def process_image(img_path, short: int = 448, long_cap: int = 448):
    img = Image.open(img_path)
    img = ImageOps.exif_transpose(img)  # honor any rotation metadata (robustness)
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size

    # Resize so the SHORT side == `short`, preserving aspect.
    if w <= h:
        new_w, new_h = short, round(h * short / w)
    else:
        new_h, new_w = short, round(w * short / h)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Center-crop: short side stays `short`; long side capped to `long_cap` (mult of 14).
    if new_w <= new_h:  # portrait → long axis is height
        cw, ch = short, _round14(min(new_h, long_cap))
    else:               # landscape → long axis is width
        cw, ch = _round14(min(new_w, long_cap)), short
    left, top = (new_w - cw) // 2, (new_h - ch) // 2
    img = img.crop((left, top, left + cw, top + ch))

    return torchvision.transforms.ToTensor()(img) * 2.0 - 1.0  # [-1, 1], CHW, RGB
