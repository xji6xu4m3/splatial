import numpy as np

from modules.reconstruct.optimize_ply import select_indices


def test_keeps_all_when_under_cap():
    a = np.array([0.1, 0.9, 0.5])
    assert list(select_indices(a, max_gaussians=10)) == [0, 1, 2]


def test_drops_below_min_alpha():
    a = np.array([0.001, 0.5, 0.002, 0.9])
    assert list(select_indices(a, max_gaussians=10, min_alpha=0.004)) == [1, 3]


def test_caps_to_highest_alpha_and_returns_sorted_indices():
    a = np.array([0.1, 0.9, 0.5, 0.7, 0.2])
    # top-2 by alpha = idx 1 (0.9) and 3 (0.7); result sorted ascending
    assert list(select_indices(a, max_gaussians=2)) == [1, 3]
