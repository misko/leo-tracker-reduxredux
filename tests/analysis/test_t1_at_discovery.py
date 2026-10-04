import numpy as np
import pytest

from leo.analysis.t1_at_discovery import discover_modes, timing_modes
from tests.analysis.test_t1_at import candidates


def test_full_bank_discovers_absolute_modes_and_shares_rf_union():
    points = tuple(
        c.model_copy(update=dict(refined_cfo_hz=1000 * 0.375 + 20 * c.receive_time_s))
        for c in candidates(20)
    )

    def predict(arm, indices, offset):
        times = np.array([c.receive_time_s for c in points])[:, None]
        # A second ID needs a large timing shift; discovery must still test it.
        p = 20 * times + 1000 * offset + np.where(indices[None, :] == 0, 0, 20000)
        p = p + (40 if arm == "zero-c" else 0)
        return p, np.ones(p.shape, bool), np.full(p.shape, 1000.0)

    result = discover_modes(points, [123, 456], predict)

    def keys(arm):
        return [(m.catalog_number, m.absolute_timing_s) for m in result[arm]]

    assert keys("fitted-c") == keys("zero-c")
    assert {m.catalog_number for m in result["fitted-c"]} == {123, 456}
    near = [m for m in result["fitted-c"] if m.catalog_number == 123]
    assert any(abs(m.absolute_timing_s - 0.375) < 0.002 for m in near)
    assert any(abs(m.absolute_timing_s - 0.335) < 0.002 for m in near)
    assert all(len(m.candidate_ids) == 20 for m in near)


def test_timing_votes_count_windows_not_repeated_coarse_hits():
    assert timing_modes([0.0] * 20, [0] * 20) == []
    assert timing_modes([0.0] * 10, list(range(10))) == [0.0]


def test_visibility_is_required():
    points = candidates(20)

    def predict(arm, indices, offset):
        shape = (len(points), len(indices))
        return np.full(shape, offset * 1000), np.zeros(shape, bool), np.full(shape, 1000.0)

    assert discover_modes(points, [1], predict) == {"fitted-c": (), "zero-c": ()}


def test_rejects_alternatives_and_bad_predictor_shape():
    points = candidates(1)
    with pytest.raises(ValueError, match="top-1"):
        discover_modes(points + points, [1], None)
    with pytest.raises(ValueError, match="shape"):
        discover_modes(points, [1], lambda *args: (np.zeros(2), np.ones(2, bool), np.ones(2)))
