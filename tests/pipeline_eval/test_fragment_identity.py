from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.qualification import fragment_identity_inputs as inputs
from tools.pipeline_eval.qualification import fragment_identity_search as search


def test_longest_eligible_published_parent_uses_span_then_count(monkeypatch):
    monkeypatch.setattr(inputs, "transfer", lambda left, right, fs: "matched_graph")
    points, old, new = [], {}, {}
    for component, span, count in (("short", 10, 30), ("longer", 40, 22), ("chosen", 40, 24)):
        for i, t in enumerate(np.linspace(0.0, span, count)):
            key = f"{component}-{i}"
            row = dict(id=key, component=component, time_s=float(t), v5_owner=17, folded_hz=400.0)
            points.append(row)
            old[key] = dict(
                id=key,
                graph=component,
                time_s=float(t),
                winner={"fractional_tracking_cfo_hz": 400.0},
            )
            new[key] = {"graph": "piece A" if i < count // 2 else "piece B"}
    chosen, _, group = inputs.nominate(points, old, new, 10_000_000)
    assert chosen["component"] == "chosen"
    assert chosen["span_s"] == 40
    assert chosen["native_points"] == len(group) == 24


def test_separate_graph_lifts_and_zero_rf_error_leave_both_pieces_predictive():
    time = np.r_[np.arange(11), 30 + np.arange(15)].astype(float)
    physics = 1000 + 80 * time**2
    by_piece = np.array(["A"] * 11 + ["B"] * 15)
    extra = np.where(by_piece == "A", 2, -1)
    target = [
        dict(graph=key, time_s=t, graph_cfo_hz=val + alias * search.FOLD_HZ)
        for key, t, val, alias in zip(by_piece, time, physics, extra, strict=True)
    ]
    support = search.Support(target)
    candidates = np.repeat(physics[None, :], len(search.PHASES), axis=0)
    fit = search.score_candidate(
        support, candidates, np.zeros(26), np.ones(len(search.PHASES)), "L3"
    )
    assert fit["alias"] == [2, -1]
    assert fit["phase_s"] == 0
    assert fit["held_loss"] < 1e-20
    assert [r["held_count"] for r in fit["folds"]] == [15, 11]
    assert fit["full_inside_450"] == 26


def test_only_fitted_c_allocates_the_cross_carrier_calibration_term():
    data = [
        dict(rx=rx, channel=ch, time_s=110.0, rf_hz=11e9 + ch * 1e8)
        for rx, ch in ((1, 1), (1, 2), (2, 7))
    ]
    zero, prior = search.features(data, "c0", 2)
    fitted, fitted_prior = search.features(data, "fitted_c", 2)
    assert len(prior) == 6 and len(fitted_prior) == 7
    assert fitted[:, :6] == pytest.approx(zero)
    assert fitted[:, -1] == pytest.approx([-0.4, -0.3, 0.2])


def test_checked_catalogue_rejects_an_unbound_result(tmp_path):
    from tools.pipeline_eval.qualification.input_factor_bridge import check

    value = Path(tmp_path / "changed")
    value.write_text("different bytes")
    with pytest.raises(ValueError, match="digest differs"):
        check(value, "0" * 64)
