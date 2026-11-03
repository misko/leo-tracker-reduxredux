from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.special import logsumexp
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402

SPEC = importlib.util.spec_from_file_location("soft_fragment_cfo_model", HERE / "model.py")
model = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = model
SPEC.loader.exec_module(model)
fast.baseline.profile = fast.profile


class LinearPrediction:
    def __init__(self, document, config):
        del config
        self.document = document

    def prediction(self, track, x):
        base = np.asarray(track["prediction"], dtype=float)
        slope = np.asarray(track["slopes"], dtype=float)
        return base + np.einsum("coj,j->co", slope, x), np.asarray(
            track.get("visible", [True] * len(base)), dtype=bool
        )


def make_track(track_id, y, prediction, slopes, *, receiver=0, rf=11.2e9):
    y = np.asarray(y, dtype=float)
    return {
        "track_id": track_id,
        "receiver_id": receiver,
        "channel": 1,
        "rf_hz": rf,
        "times_s": np.arange(len(y), dtype=float),
        "visits": np.arange(len(y)),
        "y": y,
        "mask": np.asarray([True] * (len(y) - 1) + [False]),
        "catalogue_size": 100,
        "prediction": np.asarray(prediction, dtype=float),
        "slopes": np.asarray(slopes, dtype=float),
    }


def synthetic_case(*, pair=True, gamma=None):
    slopes_a = np.asarray([
        [[1.2, -0.3, 0.1], [0.8, 0.1, -0.2], [1.0, 0.2, 0.3], [0.4, -0.1, 0.2]],
        [[-0.4, 0.7, 0.2], [-0.2, 0.5, 0.1], [-0.3, 0.6, -0.2], [0.2, 0.1, 0.3]],
    ])
    slopes_b = np.asarray([
        [[0.5, 0.4, -0.1], [0.7, 0.2, 0.2], [0.6, 0.3, 0.1], [0.1, 0.2, -0.3]],
        [[-0.1, 0.9, 0.3], [-0.4, 0.8, -0.2], [-0.2, 0.7, 0.2], [0.3, -0.2, 0.1]],
    ])
    tracks = [
        make_track("a", [110, 120, 130, 140],
                   [[10, 21, 28, 42], [50, 58, 69, 75]], slopes_a),
        make_track("b", [210, 225, 235, 250],
                   [[105, 119, 133, 148], [160, 173, 181, 198]], slopes_b),
    ]
    tracks[1]["times_s"] += 10.0
    tracks[1]["visits"] += 10
    documents = [{"session_id": "synthetic", "tracks": tracks}]
    candidates = [{"a": [11, 22], "b": [11, 22]}]
    pairs = [{
        "members": ((0, 0), (0, 1)), "candidate_norad": (11, 22),
        "frozen_norad": 11, "track_ids": ("a", "b"), "rf_hz": 11.2e9,
    }] if pair else []
    challenger = model.SoftFragmentCFO(
        documents, {}, candidates, pairs,
        "gamma1000" if gamma != math.inf else "identity_only",
        model_factory=LinearPrediction, gamma_hz=gamma,
    )
    return documents, candidates, pairs, challenger


def test_no_pair_variants_reproduce_original_iid_exactly():
    documents, candidates, _, _ = synthetic_case(pair=False)
    x = np.asarray([0.2, -0.4, 0.1])
    control = model.SoftFragmentCFO(
        documents, {}, candidates, [], "identity_only", model_factory=LinearPrediction
    )
    expected = control.evaluate(x, True)
    for variant in model.VARIANTS:
        challenger = model.SoftFragmentCFO(
            documents, {}, candidates, [], variant, model_factory=LinearPrediction
        )
        actual = challenger.evaluate(x, True)
        assert actual["score"] == pytest.approx(expected["score"], abs=1e-11)
        np.testing.assert_allclose(actual["gradient"], expected["gradient"], atol=1e-11)


def test_identity_only_common_candidate_mixture_and_one_catalogue_draw():
    documents, _, _, challenger = synthetic_case(gamma=math.inf)
    x = np.asarray([0.2, -0.4, 0.1])
    candidate_scores = []
    for slot in range(2):
        score = 0.0
        for track in documents[0]["tracks"]:
            prediction, _ = LinearPrediction(documents[0], {}).prediction(track, x)
            values = track["y"][None, :] - prediction
            profiled, _, audits, _ = fast.profile(values, track["mask"])
            assert all(row["converged"] for row in audits)
            score += profiled[slot]
        candidate_scores.append(score)
    expected = logsumexp(candidate_scores) - math.log(100)
    assert challenger.evaluate(x, False)["score"] == pytest.approx(expected, abs=1e-10)


def test_free_coupling_limit_reproduces_identity_score_gradient_and_offsets():
    _, _, _, identity = synthetic_case(gamma=math.inf)
    _, _, _, free = synthetic_case(gamma=math.inf)
    x = np.asarray([0.3, -0.2, 0.15])
    a, b = identity.evaluate(x, True), free.evaluate(x, True)
    assert a["score"] == b["score"]
    np.testing.assert_array_equal(a["gradient"], b["gradient"])
    values_a = np.asarray([-100, 0, 100, 10], dtype=float)
    values_b = np.asarray([250, 300, 350, 320], dtype=float)
    score, offsets, audit = model.profile_pair(values_a, values_b, 1.0, math.inf)
    original_a = fast.profile(values_a[None, :], np.ones(4, dtype=bool))
    original_b = fast.profile(values_b[None, :], np.ones(4, dtype=bool))
    assert score == pytest.approx(original_a[0][0] + original_b[0][0], abs=1e-10)
    np.testing.assert_allclose(offsets, [original_a[3][0], original_b[3][0]], atol=1e-8)
    assert audit["max_hessian_eigenvalue"] < 0


def test_wrapped_factor_alias_derivatives_and_pair_exchange_are_invariant():
    d = 431.2
    np.testing.assert_allclose(
        model.wrapped_terms(d, 1000),
        model.wrapped_terms(d + model.ALIAS_PERIOD_HZ, 1000),
        atol=2e-14,
    )
    a = np.asarray([-1000, -980, 970, 1010], dtype=float)
    b = np.asarray([-850, -830, 1120, 1160], dtype=float)
    first = model.profile_pair(a, b, 1.0, 1000)
    second = model.profile_pair(b, a, 1.0, 1000)
    assert first[0] == pytest.approx(second[0], abs=1e-10)
    np.testing.assert_allclose(first[1], second[1][::-1], atol=1e-7)


def test_wrapped_factor_gaussian_prior_normalizer_matches_direct_integral():
    alpha, variance = 1e-4, 1e6
    sigma = math.sqrt(2.0 * alpha * alpha * variance)
    expected = quad(
        lambda value: math.exp(model.wrapped_terms(value, 1000)[0])
        * norm.pdf(value, scale=sigma),
        -10 * sigma, 10 * sigma, epsabs=1e-11,
    )[0]
    actual = model.coupling_normalizer(alpha, 1000, variance)
    assert actual == pytest.approx(expected, abs=2e-10)
    assert model.coupling_normalizer(1.0, 1000) == 1.0


def test_multimode_profile_selects_highest_located_negative_curvature_root():
    a = np.asarray([-1030, -1000, -970, 960, 990, 1020, 1050], dtype=float)
    b = np.asarray([-900, -870, -840, 1090, 1120, 1150, 1180], dtype=float)
    score, offsets, audit = model.profile_pair(a, b, 1.0, 1000)
    assert max(audit["scalar_modes"]) >= 2
    assert audit["scalar_mode_combinations"] >= 4
    assert audit["pruned_mode_combinations"] >= 1
    assert audit["starts"] >= 2
    assert audit["roots"] >= 1
    actual_score, gradient, hessian = model.pair_objective(offsets, a, b, 1.0, 1000)
    assert actual_score == score
    assert np.max(np.abs(gradient)) < 1e-7
    assert np.max(np.linalg.eigvalsh(hessian)) < 0
    assert audit["max_hessian_eigenvalue"] < 0


def test_treatment_envelope_gradient_and_held_independence():
    documents, candidates, pairs, challenger = synthetic_case(gamma=1000)
    x = np.asarray([0.2, -0.4, 0.1])
    analytic = challenger.evaluate(x, True)
    numerical = np.empty(3)
    for axis, step in enumerate((1e-5, 1e-5, 1e-6)):
        delta = np.eye(3)[axis] * step
        numerical[axis] = (
            challenger.evaluate(x + delta, False)["score"]
            - challenger.evaluate(x - delta, False)["score"]
        ) / (2 * step)
    np.testing.assert_allclose(analytic["gradient"], numerical, atol=2e-5, rtol=0)
    held_before = challenger.held_diagnostics(x)["held_score"]
    changed = copy.deepcopy(documents)
    for track in changed[0]["tracks"]:
        track["y"][-1] += 1e8
        track["prediction"][:, -1] -= 2e8
    changed_model = model.SoftFragmentCFO(
        changed, {}, candidates, pairs, "gamma1000", model_factory=LinearPrediction
    )
    independent = changed_model.evaluate(x, True)
    assert independent["score"] == analytic["score"]
    np.testing.assert_array_equal(independent["gradient"], analytic["gradient"])
    assert changed_model.held_diagnostics(x)["held_score"] != held_before

    identity = model.SoftFragmentCFO(
        documents, {}, candidates, pairs, "identity_only", model_factory=LinearPrediction
    )
    free = model.SoftFragmentCFO(
        documents, {}, candidates, pairs, "gamma1000",
        model_factory=LinearPrediction, gamma_hz=math.inf,
    )
    assert free.held_diagnostics(x)["held_score"] == pytest.approx(
        identity.held_diagnostics(x)["held_score"], abs=1e-12
    )


def test_pair_accounting_and_candidate_guards():
    documents, candidates, pairs, _ = synthetic_case()
    duplicate = [pairs[0], pairs[0]]
    with pytest.raises(ValueError, match="unique, unshared"):
        model.SoftFragmentCFO(
            documents, {}, candidates, duplicate, "identity_only",
            model_factory=LinearPrediction,
        )
    bad = copy.deepcopy(pairs)
    bad[0]["candidate_norad"] = (999,)
    with pytest.raises(ValueError, match="candidate intersection"):
        model.SoftFragmentCFO(
            documents, {}, candidates, bad, "identity_only",
            model_factory=LinearPrediction,
        )


def test_public_builder_uses_exact_frozen_pair_membership_for_both_variants():
    base = HERE.parent.parent / "2026_09_30_ds11_single10"
    plan = json.loads((base / "plan.json").read_text())
    entry = plan["inputs"][0]
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    identity = model.build_model(documents, plan["config"], "identity_only", index=0)
    treatment = model.build_model(documents, plan["config"], "gamma1000", index=0)
    assert identity.metadata["paired_groups"] == treatment.metadata["paired_groups"] == 6
    assert [pair["track_ids"] for pair in identity.pairs] == [
        pair["track_ids"] for pair in treatment.pairs
    ]
    assert len(identity.singletons) + 2 * len(identity.pairs) == len(documents[0]["tracks"])


def test_real_no_pair_scan_matches_original_baseline_score_and_gradient():
    base = HERE.parent.parent / "2026_09_30_ds11_single10"
    plan = json.loads((base / "plan.json").read_text())
    index = 11  # Frozen fragment audit has no eligible pair in this scan.
    entry = plan["inputs"][index]
    documents = fast.load_documents({"config": plan["config"], "inputs": [entry]})
    x = np.asarray(json.loads((base / f"runs/{index:02d}_iid.json").read_text())["selected"]["x"])
    expected_score, expected_gradient = fast.baseline.Stationary(
        documents[0], plan["config"]
    ).evaluate(x, True)
    for variant in model.VARIANTS:
        challenger = model.build_model(documents, plan["config"], variant, index=index)
        assert challenger.metadata["paired_groups"] == 0
        actual = challenger.evaluate(x, True)
        assert actual["score"] == pytest.approx(expected_score, abs=1e-10)
        np.testing.assert_allclose(actual["gradient"], expected_gradient, atol=1e-10)
