import json

import numpy as np
import pytest

from tools.pipeline_eval.qualification import screening_physical as harness
from tools.pipeline_eval.qualification import screening_physical_solver as receiver


def test_differential_projection_is_affine_invariant_and_keeps_curvature():
    t = np.array([3.0, 4.2, 6.0, 8.0, 15.5, 17.0, 18.0, 23.6, 30.3])
    for u in (t[:6], t[6:]):
        q = receiver.curvature_basis(u)
        assert q.shape == (len(u), len(u) - 2)
        assert np.allclose(q.T @ q, np.eye(len(u) - 2))
        assert np.allclose(q.T @ u, 0)
        assert np.allclose(q.T @ np.ones_like(u), 0)
        y = 1e-8 * (u - u.mean()) ** 2
        assert receiver.curvature_loss(y, q) > 0
        assert receiver.curvature_loss(y + 0.025 - 0.012 * u, q) == pytest.approx(
            receiver.curvature_loss(y, q), abs=1e-8
        )
    with pytest.raises(ValueError, match="strictly increasing"):
        receiver.curvature_basis([1, 1, 2])


def test_tile_search_stays_inside_the_offer_and_nominates_on_training(monkeypatch):
    center, _ = receiver.reference._xyz([[25.0, -57.0]])
    groups = []

    def position_scores(_curves, points):
        xyz, _ = receiver.reference._xyz(points)
        assert np.all(np.linalg.norm(xyz - center, axis=1) <= 12.5)
        # Validate at the opposite edge and nominate strictly from training.
        groups.extend(points)
        return [(float(p[0]), -float(p[0]), 3, 12.0) for p in points]

    monkeypatch.setattr(receiver, "evaluate", position_scores)
    point, out = receiver.search([], [25.0, -57.0])
    assert point[0] == max(p[0] for p in groups)
    assert out["validation_score"] == -point[0]
    assert out["evaluated_locations"] == len(groups)


def test_causal_empty_input_withholds_both_calibration_arms():
    document = {"tracks": [], "catalog_timestamp_ns": 100, "cutoff_utc_ns": 101}
    result = receiver.solve(document, "")
    assert result["status"] == "withheld"
    assert result["arms"]["c0"] == result["arms"]["fitted_c"]
    assert result["arms"]["c0"]["forced_latlon"] is None
    with pytest.raises(ValueError, match="after"):
        receiver.solve(dict(document, catalog_timestamp_ns=102), "")


def test_staged_workers_have_no_scoring_coordinate_or_satellite_id():
    jobs, source, _ = harness.stage(harness.OUTPUT)
    assert len(jobs) == 12
    for row, request in jobs:
        packet = json.loads(request)
        assert set(packet) <= {"catalogue", "tile", "solver_sha256", "observation", "id"}
        assert ("tile" in packet) == (row["mode"] != "global")
        assert packet["solver_sha256"] == source["solver_sha256"]
        assert all(set(t) == harness.prior.TRACK_FIELDS for t in packet["observation"]["tracks"])
