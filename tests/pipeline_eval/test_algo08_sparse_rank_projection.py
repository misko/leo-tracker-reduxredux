from collections import Counter
from hashlib import sha256
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3 import scan as kernel
from tools.pipeline_eval.variants.algo08_sparse_rank_projection import (
    ProjectedRows,
    sparse_rank_projection,
)


def test_sparse_columns_keep_original_layout_values_and_duplicate_indices():
    rng = np.random.default_rng(21)
    base = rng.standard_normal((31, 84))
    active = np.array([0, 7, 17, 29])
    projected = rng.standard_normal((len(active), 84))
    projected[0, 10] = -0.0
    stock = base.copy()
    stock[active] = projected
    counters = Counter()
    sparse = ProjectedRows(base, active, projected, counters)
    for columns in (np.array([10, 12, 12, 20]), np.array([1, 3, 2, 13, 42, -1])):
        expected = stock[:, columns]
        actual = sparse[:, columns]
        assert actual.strides == expected.strides
        assert actual.tobytes() == expected.tobytes()
    assert counters["materialized_bytes"] == 0
    assert sparse[[2, 1], 13].tobytes() == stock[[2, 1], 13].tobytes()
    assert np.asarray(sparse).tobytes() == stock.tobytes()
    assert counters["materialized_bytes"] == base.nbytes


def test_native_projection_uses_the_same_sky_rows_phases_and_site(monkeypatch):
    scan = object.__new__(kernel.ScanLikelihood)
    scan.times = np.arange(11.)
    scan.center = (41., 8.)
    scan.scale = 75.
    scan.sky = dict(time_s=scan.times, position_km=np.arange(132.).reshape(4, 11, 3),
                    velocity_km_s=np.arange(132.).reshape(4, 11, 3) + 21.)
    phases = np.array([0., 1.2, 1e-11, -0.3])
    point = np.array([10., 5.])
    base = (np.ones((4, 11)), np.zeros((4, 11)), np.full((4, 11), -3.))

    def configure(sky, times, chosen):
        assert times is scan.times
        np.testing.assert_array_equal(sky["position_km"], scan.sky["position_km"][[1, 3]])
        np.testing.assert_array_equal(chosen, np.array([1.2, -0.3]))
        return sky

    def evaluate(sky, lat, lon):
        assert (lat, lon) == scan.latlon(point)
        projected = sky["velocity_km_s"][:, :, 0].copy()
        return projected, -projected, 2 * projected

    monkeypatch.setattr(kernel, "prepare_phase_geometry", configure)
    monkeypatch.setattr(kernel, "phase_linear_frequency", evaluate)
    expected = scan.shifted(base, phases, point)
    source_digest = sha256(Path(kernel.__file__).read_bytes()).hexdigest()
    index = np.array([4, 6, 6, 2, 10])
    with sparse_rank_projection(scan, expected_source_sha256=source_digest) as counts:
        actual = scan.shifted(base, phases, point)
        for a, b in zip(actual, expected, strict=True):
            assert a[:, index].tobytes() == b[:, index].tobytes()
        assert counts["active_rows"] == 2
        assert counts["catalogue_rows"] == 4
        assert counts["column_requests"] == 3
        assert counts["materialized_bytes"] == 0
    assert scan.shifted.__func__ is kernel.ScanLikelihood.shifted
