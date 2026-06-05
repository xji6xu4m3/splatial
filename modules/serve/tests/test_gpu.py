import pytest
from modules.serve.gpu import default_max_views

GB = 1024 ** 3

@pytest.mark.parametrize("vram_gb, expected", [
    (8, 16), (11.5, 16), (12, 16),     # <=12GB cards (4070 Ti) -> 16
    (16, 32), (24, 32), (32, 32),      # 16-24GB (3090/4090) -> 32
    (40, 48), (48, 48), (80, 48),      # >=40GB (A100/L40S) -> 48
    # realistic reported VRAM (torch reads under nominal, driver reserve):
    (11.7, 16),                        # 12GB card
    (15.6, 32), (23.6, 32),            # 16GB / 24GB cards
    (39.5, 48), (79.3, 48),            # 40GB / 80GB A100
])
def test_default_max_views(vram_gb, expected):
    assert default_max_views(int(vram_gb * GB)) == expected

def test_zero_or_unknown_falls_back_to_16():
    assert default_max_views(0) == 16
    assert default_max_views(None) == 16
