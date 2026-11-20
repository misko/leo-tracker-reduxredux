import numpy as np
import pytest
from scipy.optimize import lsq_linear

from tools.pipeline_eval.qualification import orbit_influence_trial as trial
from tools.pipeline_eval.variants import orbit_influence as influence


def test_deleted_normal_blocks_match_bounded_rectangular_refits():
    rng = np.random.default_rng(44)
    labels = np.repeat([18, 25, 29, 34], 5)
    data = rng.normal(size=(len(labels), 4))
    design = np.vstack([data, 0.4 * np.eye(4)])
    response = np.r_[data @ [3.0, 1.5, 1.0, 1.6] + 0.1 * rng.normal(size=len(data)), np.zeros(4)]
    original_bounds = (np.full(4, -0.5), np.full(4, 0.5))
    tested, covariance, shifts = influence.normal_deletions(
        design, response, labels, original_bounds
    )
    lower = [-np.inf, -np.inf, -0.5, -0.5]
    upper = [np.inf, np.inf, 0.5, 0.5]
    full = lsq_linear(design, response, bounds=(lower, upper), method="bvls").x[:2]
    assert tested == pytest.approx(full, abs=1e-10)
    assert covariance == pytest.approx(np.linalg.inv(design.T @ design)[:2, :2])
    for orbit in set(labels):
        keep = np.r_[labels != orbit, np.ones(4, dtype=bool)]
        deleted = lsq_linear(design[keep], response[keep], bounds=(lower, upper), method="bvls")
        assert shifts[orbit] == pytest.approx(deleted.x[:2] - full, abs=1e-10)


def test_ellipse_and_every_delete_point_must_be_strictly_inside():
    local = np.eye(2) * 0.04
    shifts = np.array([[0.1, 0.0], [-0.1, 0.0], [0.05, 0.2]])
    centered = influence.containment(np.zeros(2), 12.5, local, shifts)
    assert centered["admitted"]
    grazing = influence.containment(np.array([12.4, 0.0]), 12.5, local, shifts)
    assert not grazing["admitted"]
    assert grazing["ordinary_margin_km"] > 0
    assert grazing["ellipse_margin_km"] < 0
    assert grazing["deletion_margin_km"] == pytest.approx(0)


def test_live_native_graph_and_original_fit_parity_are_required():
    original = dict.fromkeys(
        ("id", "recording", "input_sha256", "native_sha256", "catalog_sha256", "tile"), "bound"
    )
    result = dict(status="ok", reason=None, arms={}, metrics=dict(clock_fit={"fixed": True}))
    stock = dict(original, result=result, observation_sha256="graph")
    live = dict(stock, ungated=result)
    assert trial.bind_fresh(live, stock) is live
    with pytest.raises(ValueError, match="archived smooth fit"):
        trial.bind_fresh(dict(live, observation_sha256="wrong"), stock)
