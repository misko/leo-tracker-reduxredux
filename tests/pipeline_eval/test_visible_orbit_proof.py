from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def kernel(monkeypatch):
    from tools.pipeline_eval.variants.experimental import regional_reassignment

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return regional_reassignment


def geometry(position, velocity, dp, dv):
    from leo.analysis.research.phase_linear_geometry import PreparedPhaseGeometry
    from leo.analysis.research.track_catalogue_geometry import PreparedGeometry

    def dot(a, b):
        return np.einsum("snj,snj->sn", a, b)

    base = PreparedGeometry(position, velocity, dot(position, position), dot(position, velocity))
    return PreparedPhaseGeometry(base, dp, dv, dot(dp, velocity) + dot(position, dv), dot(position, dp))


def test_visibility_first_preserves_released_scores_and_label_ties(kernel):
    from visible_orbit_proof import VisibleProjection

    rng = np.random.default_rng(9)
    position = rng.normal((6378.137, 1100., 200.), (150., 40., 60.), size=(31, 13, 3))
    position[[0, 1], :, 0] = 6378.137  # Exact horizon for the equatorial station.
    position[1] = position[0]
    position[2, :, 0] += 800
    velocity, dp, dv = [rng.normal(size=position.shape) for _ in range(3)]
    for values in (velocity, dp, dv):
        values[1] = values[0]
    bank = geometry(position, velocity, dp, dv)
    counts = Counter()
    labels = np.arange(100, 131)
    nav = [(0., 0.), (.3, -.5), (0., 180.)]
    for coordinate in nav:
        f, e, d = kernel.phase_linear_frequency(bank, *coordinate)
        sparse = VisibleProjection(bank, *coordinate, kernel, counts)
        np.testing.assert_array_equal(sparse.visible, e >= 0)
        for indices in (np.array([1]), np.array([2, 3, 8, 12]), np.array([0, 7, 7, 10])):
            q = 1.024
            measured = q * f[0, indices].copy()
            expected = kernel.score_track(measured, q * f[:, indices], e[:, indices], q * d[:, indices], labels, 611)
            assert sparse.score(measured, indices, q, labels, 611) == expected
    assert counts["track_trials"] == 3 * len(nav)
    assert 0 < counts["track_projection_cells"] < counts["full_projection_cells"]


@pytest.mark.parametrize("sparse_failure", (False, True))
def test_rewrite_preserves_probe_arithmetic_and_replays_stock_for_unsupported_projection(kernel, monkeypatch, sparse_failure):
    import visible_orbit_proof as candidate

    positions = np.array([[[7500., 200., 120.], [7500., 201., 118.]],
                          [[-7500., 200., 120.], [-7500., 201., 118.]]])
    velocities = np.zeros(positions.shape)
    bank = geometry(positions, velocities, velocities, velocities)
    catalogue = SimpleNamespace(satellite_numbers=(81, 82, 900))
    region = SimpleNamespace(center=(0., 0.))
    data = dict(observations=[dict(observation_id=i, receiver=1) for i in range(2)],
                tracks=[dict(observation_ids=[0, 1], receiver=1, times=np.array([1., 2.]),
                             key="track", rf_hz=11.5e9, values=np.zeros(2))], metadata=dict(anchor_utc_ns=0))
    monkeypatch.setattr(kernel, "probes", lambda _: [dict(latlon=(0., 0.))])
    monkeypatch.setattr(kernel, "orbit_geometry", lambda *args: (bank, np.array([81, 82])))
    expected = kernel.evaluate(data, catalogue, region)
    if sparse_failure:
        def invalid(*args):
            raise ValueError("unsupported range")

        monkeypatch.setattr(candidate, "VisibleProjection", invalid)
    stock, counts = kernel._prepare_probe_scores, Counter()
    monkeypatch.setattr(kernel, "_prepare_probe_scores", candidate.source_binding(kernel, stock, counts))
    assert kernel.evaluate(data, catalogue, region) == expected
    assert counts["dense_fallback_probes" if sparse_failure else "sparse_probes"] == 1
