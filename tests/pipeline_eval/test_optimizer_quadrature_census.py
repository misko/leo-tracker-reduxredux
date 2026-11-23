from pathlib import Path
import sys
from types import MethodType

import numpy as np

from tools.pipeline_eval.variants.compact_cavity_optimizer import MIN_DECREASE, bounded_secant

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from optimizer_quadrature_census import Census, attribution


def test_stock_observer_keeps_every_exact_step_and_classifies_full_calls():
    class Example:
        fitted_c = False
        keep = np.ones(2, dtype=bool)

        def residual(self, position):
            return (position-np.array([1.5, .75]))**3

    point = np.zeros(2)
    lo, hi = [-10., -10.], [10., 10.]
    stock = bounded_secant(Example().residual, point, lo, hi)
    original = Example()
    census = Census()
    traced = MethodType(census.residual(Example.residual, lambda _: True, MIN_DECREASE), original)
    trial = bounded_secant(traced, point, lo, hi)
    assert np.array_equal(stock["parameters"], trial["parameters"])
    assert stock["score"] == trial["score"]
    assert len(census.rows) == stock["evaluations"]
    arm = attribution(census.rows, census.fits)["post_cold"]["c0"]
    assert arm["starting"]["calls"] == 1
    assert arm["derivative"]["calls"] == stock["jacobian_refreshes"]*2
    assert arm["trust_accepted"]["calls"] == len(stock["history"])-1
    assert arm["trust_rejected"]["calls"] == stock["rejected_trials"]
    assert arm["final_derivative"]["calls"] == 2


def test_ceiling_retains_starts_backtracks_cold_no_move_and_final_checks():
    fits = [dict(stage=stage, arm="c0", temporal_eligible=True) for stage in ("cold", "ordinary")]
    rows = []
    for fit in (0, 1):
        rows.append(dict(fit=fit, refresh=0, role="start", cpu_ns=1))
        for refresh in (1, 2, 3):
            rows.extend(dict(fit=fit, refresh=refresh, role="derivative", cpu_ns=10,
                             curved_ns=2) for _ in range(2))
        rows.extend([
            dict(fit=fit, refresh=1, role="trust", accepted=False, cpu_ns=4),
            dict(fit=fit, refresh=2, role="trust", accepted=True, cpu_ns=5),
            dict(fit=fit, refresh=3, role="trust", accepted=True, cpu_ns=6),
        ])
    post = attribution(rows, fits)["post_cold"]["c0"]
    assert post["derivative"]["cpu_ns"] == 60
    assert post["removable"]["cpu_ns"] == 20
    assert post["removable"]["curved_ns"] == 4
    assert post["final_derivative"]["cpu_ns"] == 20
    assert post["trust_accepted"]["cpu_ns"] == 11
    assert post["trust_rejected"]["cpu_ns"] == 4
