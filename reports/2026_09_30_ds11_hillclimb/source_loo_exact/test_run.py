from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ds11_source_loo_exact_run_test", HERE / "run.py")
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


def assignment(track, norad, unambiguous=True):
    return {"track_id": track, "norad": norad, "unambiguous": unambiguous}


def test_groups_span_receiver_rf_semantics_by_using_only_physical_norad():
    rows = [assignment("a", 10), assignment("b", 10), assignment("c", 20),
            assignment("d", None, False)]
    assert runner.eligible_groups(rows) == {10: [0, 1]}


def test_retained_source_weights_are_subset_without_renormalization():
    rows = [assignment("a", 10), assignment("b", 10), assignment("c", 20),
            assignment("d", None, False)]
    weights = np.asarray([0.25, 0.5, 0.75, 1.0])
    fold = runner.retained_fold(rows, weights, 10)
    assert fold["omitted_indices"] == [0, 1]
    assert fold["retained_indices"] == [2, 3]
    np.testing.assert_array_equal(fold["retained_weights"], [0.75, 1.0])
    assert fold["retained_weights"].sum() != weights.sum()


class Quadratic:
    def evaluate(self, x, gradient=True):
        displacement = np.asarray(x) - np.asarray([1.0, -2.0, 0.5])
        return {"score": float(-0.5 * displacement @ displacement), "gradient": -displacement}


def test_fit_local_uses_one_supplied_seed_and_frozen_optimizer_options():
    captured = {}

    class Result:
        x = np.asarray([1.0, -2.0, 0.5])
        fun = 0.0
        jac = np.zeros(3)
        success = True
        message = "ok"
        nfev = 1
        nit = 1

    def fake_minimize(objective, seed, **kwargs):
        captured["seed"] = np.asarray(seed)
        captured.update(kwargs)
        value, gradient = objective(np.asarray(seed))
        assert np.isfinite(value) and np.isfinite(gradient).all()
        return Result()

    def fake_qualify(result, model, bounds):
        assert isinstance(model, Quadratic)
        return {"qualified": result.success}

    seed = np.asarray([0.2, 0.3, -0.1])
    _, qualification = runner.fit_local(
        Quadratic(), seed, np.asarray([[-12, 12], [-12, 12], [-5, 5]]),
        fake_qualify, minimize_fn=fake_minimize,
    )
    np.testing.assert_array_equal(captured["seed"], seed)
    assert captured["method"] == "L-BFGS-B"
    assert captured["options"] == {"maxiter": 100, "maxfun": 160, "ftol": 1e-13,
                                    "gtol": 1e-6, "maxls": 25}
    assert qualification["qualified"]


def family_row(family, score, qualified=True, coverage=None):
    return {"family": family, "family_qualified": qualified,
            "common_held_sum": score, "coverage": coverage or [{"norad": 1}]}


def test_selection_requires_full_qualification_and_identical_coverage():
    rows = [family_row(family, float(index)) for index, family in enumerate(runner.FAMILY_ORDER)]
    assert runner.select_family(rows)["selected_family"] == "robust_t4_scale200"
    tied = [family_row(family, 1.0) for family in runner.FAMILY_ORDER]
    assert runner.select_family(tied)["selected_family"] == "iid_t4_scale100"
    unqualified = [dict(row) for row in rows]
    unqualified[2]["family_qualified"] = False
    assert runner.select_family(unqualified)["reason"] == "unqualified_fold"
    mismatch = [dict(row) for row in rows]
    mismatch[3]["coverage"] = [{"norad": 2}]
    assert runner.select_family(mismatch)["reason"] == "coverage_mismatch"


def test_fixed_family_and_screen_sets_have_no_extra_variants():
    assert runner.FAMILY_ORDER == ("iid_t4_scale100", "source_receiver_equal",
                                   "robust_t8_scale100", "robust_t4_scale200")
    assert runner.SCREEN == (0, 4, 8, 12, 16, 20, 24, 28)
    assert runner.PILOT_INDEX == 0
    assert runner.CURRENT_RUN_INDICES == (0,)
