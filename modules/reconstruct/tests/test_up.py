import numpy as np
from modules.reconstruct.anysplat_provider import up_from_extrinsics, up_from_plane


def test_up_from_extrinsics_identity_cameras_point_down():
    # Identity cam2world: camera +Y (down) == world +Y, so world-up = -mean = [0,-1,0].
    c2w = np.stack([np.eye(4) for _ in range(5)])
    assert np.allclose(up_from_extrinsics(c2w), [0.0, -1.0, 0.0], atol=1e-6)


def test_up_from_extrinsics_camera_rolled_180_about_x():
    # Rotate 180° about X: camera +Y now points to world -Y, so world-up = [0,1,0].
    R = np.diag([1.0, -1.0, -1.0])
    c2w = np.zeros((4, 4, 4))
    for i in range(4):
        c2w[i, :3, :3] = R
        c2w[i, 3, 3] = 1.0
    assert np.allclose(up_from_extrinsics(c2w), [0.0, 1.0, 0.0], atol=1e-6)


def test_up_from_extrinsics_rejects_bad_shape():
    assert up_from_extrinsics(np.zeros((0, 4, 4))) is None
    assert up_from_extrinsics(np.eye(4)) is None  # not [V,4,4]


def test_up_from_plane_finds_floor_normal_with_prior_sign():
    rng = np.random.default_rng(0)
    pts = np.column_stack([rng.uniform(-1, 1, 4000), rng.uniform(-1, 1, 4000),
                           np.full(4000, 0.5)])  # flat plane at z=0.5, normal = ±Z
    bbox = [[-1, -1, 0], [1, 1, 1]]
    up = np.asarray(up_from_plane(pts, up_prior=[0, 0, 1], bbox=bbox))
    assert abs(float(np.dot(up, [0, 0, 1]))) > 0.99   # aligned with Z
    assert float(np.dot(up, [0, 0, 1])) > 0            # prior fixed the sign to +Z
