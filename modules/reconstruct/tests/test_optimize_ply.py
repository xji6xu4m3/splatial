import numpy as np

from modules.reconstruct.optimize_ply import select_indices


def test_keeps_all_when_under_cap():
    a = np.array([0.1, 0.9, 0.5])
    assert list(select_indices(a, max_gaussians=10)) == [0, 1, 2]


def test_drops_below_min_alpha():
    a = np.array([0.001, 0.5, 0.002, 0.9])
    assert list(select_indices(a, max_gaussians=10, min_alpha=0.004)) == [1, 3]


def test_caps_with_uniform_subsample_keeps_count_sorted_unique_and_in_range():
    a = np.linspace(0.01, 0.99, 1000)
    idx = select_indices(a, max_gaussians=300, min_alpha=0.0, seed=0)
    assert idx.size == 300
    assert list(idx) == sorted(idx)              # sorted ascending
    assert len(set(idx.tolist())) == 300         # unique
    assert idx.min() >= 0 and idx.max() < 1000


def test_subsample_is_deterministic_for_seed():
    a = np.linspace(0.01, 0.99, 1000)
    assert list(select_indices(a, 300, seed=7)) == list(select_indices(a, 300, seed=7))


def test_subsample_preserves_background_not_just_high_opacity():
    # 900 low-opacity "background" + 100 high-opacity "foreground"; a uniform 500-sample
    # must keep plenty of background (opacity-ranked pruning would keep ~0 background).
    a = np.concatenate([np.full(900, 0.05), np.full(100, 0.95)])
    idx = select_indices(a, max_gaussians=500, seed=0)
    kept_background = int((idx < 900).sum())
    assert kept_background > 300  # background well-represented
