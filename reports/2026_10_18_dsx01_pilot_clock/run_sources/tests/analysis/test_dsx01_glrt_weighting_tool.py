"""Score joins and heteroscedastic variance are independent of satellite fits."""

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def tools():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield (
            importlib.import_module("export_dsx01_glrt_scores"),
            importlib.import_module("prototype_dsx01_glrt_weighting"),
        )
    finally:
        sys.path.remove(path)


def test_score_join_preserves_ids_and_checks_every_winning_cfo(tools):
    export, _ = tools

    def probe(counter, cfo, margin):
        return dict(
            receiver_id=0,
            channel=2,
            valid_start_counter=counter,
            actual_rf_hz=11e9,
            candidates=[
                dict(
                    candidate_rank=0,
                    fractional_margin=margin,
                    fractional_tracking_cfo_hz=cfo,
                    fractional_exact_score=margin + 0.01,
                    fractional_control_score=0.01,
                    passed_fractional_margin_gate=True,
                )
            ],
        )

    document = dict(probes=[probe(200, 120, 0.4), probe(100, 110, 0.1)])
    context = [
        dict(
            observation_id=f"id-{k}",
            receiver=1,
            channel=2,
            time_s=t,
            measured_cfo_hz=f,
            actual_rf_hz=11e9,
        )
        for k, t, f in [(1, 3.2, 120), (0, 2.1, 110)]
    ]
    scores = export.score_records(document, context)
    assert scores["id-0"]["fractional_margin"] == 0.1
    assert scores["id-1"]["valid_start_counter"] == 200
    context[0]["measured_cfo_hz"] += 1
    with pytest.raises(ValueError, match="CFO"):
        export.score_records(document, context)
    with pytest.raises(ValueError, match="count"):
        export.score_records(document, context[:1])


def test_variance_profile_recovers_exact_conditional_variance(tools):
    _, weight = tools
    margins = np.geomspace(0.025, 0.7, 500)
    fitted = weight.fit_variance(margins, 6400 + 2000 / margins)
    np.testing.assert_allclose(fitted, [6400, 2000], rtol=1e-6)
    constant = weight.fit_variance(margins, np.full(len(margins), 10000.0))
    np.testing.assert_allclose(constant, [10000, 0], atol=0.01)
    with pytest.raises(ValueError):
        weight.fit_variance(np.array([0]), np.array([1]))


def test_polynomial_leverage_correction_uses_original_curved_samples_only(tools):
    _, weight = tools
    from types import SimpleNamespace

    t = np.linspace(0, 100, 21)
    ids = [str(k) for k in range(21)]
    y = 3 * t + 2 + np.sin(t)
    track = dict(
        times=t, values=y, observation_ids=ids, pieces=[dict(degree=1, observation_ids=ids)]
    )
    scan = SimpleNamespace(tracks=[track, track], curved=[0])
    scores = {oid: dict(fractional_margin=0.2) for oid in ids}
    m, sq = weight.variance_samples(scan, scores)
    assert len(m) == 21
    q, _ = np.linalg.qr(np.column_stack((np.ones(21), t)))
    expected = (y - q @ (q.T @ y)) ** 2 / (1 - np.sum(q * q, axis=1))
    np.testing.assert_allclose(sq, expected, atol=1e-10)
