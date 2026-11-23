from importlib import import_module
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def audit(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    monkeypatch.syspath_prepend(str(directory))
    return import_module("proof_cold_reuse")


def test_proof_slates_count_missing_votes_and_keep_cold_fallback(audit):
    probes = [{"owners": dict(stable=a, tied=b, unseen=c, intermittent=d)} for a, b, c, d in zip(
        (10, 10, 10, 11, None), (10, 10, 10, 11, 12), (18, 18, 18, 18, 18), (10, 11, 12, None, None), strict=True)]
    fits, votes = audit.admissible(probes, ["stable", "tied", "unseen", "intermittent"], [10, 11, 12])
    assert fits == {"stable": [10, 11]}
    assert votes["tied"] == {10: 3, 11: 1, 12: 1}
    assert votes["unseen"] == {18: 5}


def test_weighted_ceiling_rejects_admitted_track_missing_original_alias_owner(audit):
    probes = [{"owners": {"a": 10, "b": None}}] * 5
    summary = audit.projections(probes, {"a": 20, "b": 5}, [10, 20, 30], [[("a", 1, 20, -1), ("b", 2, 30, 0)]])
    assert summary["baseline_cells"] == 75 and summary["capped_cells"] == 35
    assert summary["fallback_tracks"] == 1 and not summary["warrants_trial"]
    rank, = summary["ranks"]
    assert rank["misses"]["capped_with_fallback"] == [dict(component="a", norad=20, alias=-1, points=20)]
    assert rank["hits"] == {"track_union": 0, "capped_with_fallback": 1, "global_union": 0}


def test_geographic_contrast_cancels_all_constant_carrier_rolls(audit):
    from tools.pipeline_eval.variants.experimental.regional_reassignment import PERIOD, contrast_log_ratio

    observed = np.array([-136.3, -85.4, -7.5, 77.9])
    predicted = np.array([[-150., -60., -12., 99.]])
    derivative = np.array([[8., 10., 11., 20.]])
    original = contrast_log_ratio(observed, predicted, derivative)
    for alias in (-3, -1, 1, 3):
        np.testing.assert_allclose(contrast_log_ratio(observed, predicted + alias * PERIOD, derivative),
                                   original, atol=1e-10, rtol=0.)
