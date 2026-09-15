import numpy as np
import pytest

from leo.analysis.research.scanner_tle_screen import rank_curves, sample_grid


def test_future_cannot_change_selected_candidate_offset_or_tau():
    t = np.arange(20.0)
    p = np.array([[t, t + 0.1 * t * t], [-t, -t + 0.1 * t * t]])
    y = t + 17
    before = rank_curves(y, p, training_count=12)
    y[12:] = -1000
    after = rank_curves(y, p, training_count=12)
    for key in ("order", "tau_indices", "offsets", "training_rms"):
        np.testing.assert_array_equal(before[key], after[key])
    assert before["order"][0] == 0
    assert before["heldout_rms"][0] == 0
    assert after["heldout_rms"][0] > 1000


def test_interpolation_preserves_linear_doppler_and_rejects_extrapolation():
    grid = np.array([[0.0, 2.0, 4.0], [10.0, 8.0, 6.0]])
    np.testing.assert_allclose(sample_grid(grid, 0, 1, [0.5, 1.5]), [[1, 3], [9, 7]])
    with pytest.raises(ValueError):
        sample_grid(grid, 0, 1, [2.01])


def test_invalid_bank_rejected():
    with pytest.raises(ValueError):
        rank_curves([1, 2, 3], np.ones((2, 3, 4)), training_count=2)


def test_missing_analysis_is_retried_when_review_resumes(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import tools.review_rx0_scanner_tles as tool

    sid = "scan-hop-test"
    (tmp_path / (sid + ".json")).write_text(json.dumps({"session_id": sid, "error": "old failure"}))

    def inspect(_):
        raise ValueError("retried source")

    monkeypatch.setattr(
        tool,
        "ScannerTrackingInputStore",
        lambda *a, **k: SimpleNamespace(close=lambda: None),
    )
    monkeypatch.setattr(
        tool,
        "AdaptiveHopIqStore",
        lambda *a, **k: SimpleNamespace(inspect=inspect, close=lambda: None),
    )
    result = tool.review(({"session_id": sid}, str(tmp_path), None))
    assert result["error"] == "ValueError: retried source"
