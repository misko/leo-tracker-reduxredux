import numpy as np

from tools.pipeline_eval.variants import orbit_proposals as model


def test_circular_range_derivatives_recover_two_ground_signs():
    r, w = 6921, 0.0011
    xyz = np.array([r, 0.0, 0.0])
    v = np.array([0.0, w * r, 0.0])
    a, b = 0.99, 0.065
    z = np.sqrt(1 - a**2 - b**2)
    rho = np.sqrt(r**2 + model.EARTH**2 - 2 * r * model.EARTH * a)
    u = -model.EARTH * r * w * b / rho
    acceleration = (r * model.EARTH * w**2 * a - u**2) / rho
    jerk = -u * (w**2 + 3 * acceleration / rho)
    seeds = model.inverse(xyz[None], v[None], acceleration, jerk)
    np.testing.assert_allclose(seeds, [[a, b, z], [a, b, -z]], atol=2e-6)
    assert model.inverse(xyz[None], v[None], 0.0, jerk).shape == (0, 3)
    assert model.inverse(xyz[None], v[None], 2 * acceleration, 10).shape == (0, 3)


def test_consensus_uses_distinct_time_blocks_and_finds_planted_coordinate():
    earth = np.eye(3)
    point = np.array([1.0, -0.15, 0.4])
    point /= np.linalg.norm(point)
    assert model.nominate([(1, earth), (2, earth), (2, earth)])[0] == []
    centers, blocks = model.nominate([(i, np.vstack((point, v))) for i, v in enumerate(earth)])
    assert blocks == 3
    assert any(np.linalg.norm(np.subtract(p, model.as_latlon(point))) < 1 for p in centers)
