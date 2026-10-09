"""Actual fresh-calibration flow tests with synthetic objective and bounded fitter."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("direct_chain103", Path(__file__).with_name("run.py"))
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def setup(monkeypatch, *, converged):
    vector = np.arange(10, dtype=float)
    prefit = SimpleNamespace(vector=vector.copy())
    observed_terms = object()
    evaluations = []

    def evaluate(seed):
        evaluations.append(seed.copy())
        return 0, np.zeros(10), observed_terms

    base = SimpleNamespace(bank=object(), evaluate=evaluate)
    correction = dict(values_hz=np.array([4.0, 5.0]), knots_hz=np.zeros((2, 3)))
    correction_object = SimpleNamespace(**correction)

    def receiver_correction(observations, terms):
        assert terms is observed_terms
        return correction_object

    monkeypatch.setattr(driver.continuation, "receiver_correction", receiver_correction)
    actual_json = driver.continuation.json_value
    monkeypatch.setattr(
        driver.continuation,
        "json_value",
        lambda item: actual_json(correction) if item is correction_object else actual_json(item),
    )
    corrected = SimpleNamespace(design=np.ones((2, 4)))

    def model(*args, **kwargs):
        np.testing.assert_array_equal(kwargs["receiver_baseline_hz"], [4, 5])
        return corrected

    monkeypatch.setattr(driver.continuation, "Hard60Objective", model)

    def fit(start):
        return driver.continuation.PositionFit(
            start.copy(),
            123.0,
            3.0,
            50.0,
            0.0001 if converged else 0.01,
            converged,
            False,
            "synthetic",
            17,
            0.02,
        )

    fit_calls = []

    def bounded(objective, start, **options):
        assert objective is corrected
        fit_calls.append((start.copy(), options))
        return fit(start), {"solver_success": True}

    monkeypatch.setattr(driver.continuation, "fit_bounded_position", bounded)
    validated = []

    def validate(objective, saved, point):
        assert objective is corrected
        validated.append(saved)
        return driver.continuation.PositionFit(
            np.asarray(saved["vector"]),
            saved["objective"],
            3.0,
            50.0,
            0.0001,
            True,
            False,
            "verified",
            saved["evaluations"],
            0.02,
        )

    monkeypatch.setattr(driver, "validated_postfit", validate)
    monkeypatch.setattr(
        driver.continuation,
        "RegionalCalibration",
        lambda indices, before, after, correction, baseline: {
            "indices": list(indices),
            "prefit_vector": before.vector.tolist(),
            "postfit_vector": after.vector.tolist(),
            "baseline": baseline.tolist(),
        },
    )
    return prefit, base, evaluations, fit_calls, validated


def test_already_qualified_fresh_postfit_skips_polish(monkeypatch):
    prefit, base, evaluations, fits, validated = setup(monkeypatch, converged=True)
    monkeypatch.setattr(
        driver.qualification, "qualify", lambda *args, **kwargs: pytest.fail("No extra polish")
    )
    result = driver.fresh_calibration(object(), base, object(), [0, 1], prefit)
    assert result["status"] == "qualified" and result["qualification"] is None
    np.testing.assert_array_equal(evaluations[0], prefit.vector)
    assert len(fits) == 1 and len(validated) == 1
    assert fits[0][1] == dict(
        fixed_position=True,
        rf_arm="fitted-c",
        slope_half_width_hz_s=60,
        maximum_seconds=20,
        maximum_iterations=600,
    )
    np.testing.assert_array_equal(
        result["calibration"]["baseline"], np.array([4, 5]) + sum(prefit.vector[2:6])
    )


@pytest.mark.parametrize("rescued", [False, True])
def test_exactly_one_direct_polish_on_independent_failure(monkeypatch, rescued):
    prefit, base, evaluations, fits, validated = setup(monkeypatch, converged=False)
    calls = []

    def qualify(objective, seed, saved_score, **options):
        calls.append(options)
        selected = seed.copy()
        selected[2] += 5
        return dict(
            status="qualified" if rescued else "unqualified",
            qualified=rescued,
            fit={
                "vector": selected.tolist(),
                "objective": 122.0,
                "evaluations": 46,
                "converged": rescued,
            },
        )

    monkeypatch.setattr(driver.qualification, "qualify", qualify)
    result = driver.fresh_calibration(object(), base, object(), [0, 1], prefit)
    assert calls == [
        dict(
            retained=True,
            stage="calibration-postfit",
            independently_qualified=False,
            maximum_rounds=2,
            maximum_evaluations=100,
        )
    ]
    assert len(fits) == 1
    assert result["status"] == ("qualified" if rescued else "calibration-unqualified")
    assert len(validated) == int(rescued)
    if rescued:
        assert result["calibration"]["postfit_vector"][2] == prefit.vector[2] + 5
    else:
        assert result["calibration"] is None


@pytest.mark.parametrize("failure", ["missing", "timeout"])
def test_missing_saved_postfit_does_not_invent_polish_seed(monkeypatch, failure):
    prefit, base, *_ = setup(monkeypatch, converged=False)

    def failed(*args, **kwargs):
        if failure == "timeout":
            raise TimeoutError("no saved state")
        return None, {}

    monkeypatch.setattr(driver.continuation, "fit_bounded_position", failed)
    monkeypatch.setattr(
        driver.qualification, "qualify", lambda *args, **kwargs: pytest.fail("No saved seed")
    )
    result = driver.fresh_calibration(object(), base, object(), [0, 1], prefit)
    assert result["status"] == "calibration-failed" and result["calibration"] is None


@pytest.mark.parametrize("bad", [None, "position", "objective", "gate", "feasible"])
def test_postfit_independent_validation(monkeypatch, bad):
    vector = np.arange(10, dtype=float)
    saved = dict(vector=vector.tolist(), objective=10.0, converged=True, evaluations=46)
    if bad == "position":
        saved["vector"][0] = 99
    if bad == "objective":
        saved["objective"] = 9

    class Problem:
        def __init__(self, objective, seed, **options):
            assert options == dict(fixed_position=True, rf_arm="fitted-c", slope_half_width_hz_s=60)

        def stationarity(self, vector, gradient):
            return 0.01 if bad == "gate" else 0.0001

        def feasible(self, vector):
            return bad != "feasible"

    monkeypatch.setattr(driver.continuation, "_Problem", Problem)
    model = SimpleNamespace(
        evaluate=lambda seed: (
            10.0,
            np.zeros(10),
            SimpleNamespace(
                responsibilities=np.array([[1.0, 1.0]]), residual_hz=np.array([[2.0, 2.0]])
            ),
        )
    )
    if bad:
        with pytest.raises(AssertionError):
            driver.validated_postfit(model, saved, vector[:2])
    else:
        result = driver.validated_postfit(model, saved, vector[:2])
        assert result.converged and result.posterior_rms_hz == 2


def test_main_only102prefit_fresh_calibration_then_immutable_downstream(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(driver, "HERE", tmp_path)
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    monkeypatch.setattr(driver, "SOURCE", source)
    monkeypatch.setattr(driver.continuation, "PARENT", tmp_path)
    plan = dict(
        source_sha256={}, direct_postfit_polish_rounds=2, direct_postfit_polish_evaluations=100
    )
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    (source / "protocol.json").write_text("{}")
    seed = np.arange(10, dtype=float)
    (source / "result.json").write_text(
        json.dumps(
            dict(
                protocol_sha256=hashlib.sha256(b"{}").hexdigest(),
                attempts={
                    "calibration-prefit": {
                        "qualified": True,
                        "objective_verified": True,
                        "fit": {"vector": seed.tolist()},
                    }
                },
            )
        )
    )
    (tmp_path / "published-v3.json").write_text(json.dumps({"manifest": {"document": {}}}))
    (tmp_path / "verified-checkpoints.json").write_text(
        json.dumps({"selected_basin": {"east_km": seed[0], "north_km": seed[1]}})
    )
    base = object()
    monkeypatch.setattr(
        driver.continuation, "load_case", lambda *args: ("obs", "bank", "prior", base, [1])
    )
    monkeypatch.setattr(
        driver.continuation,
        "select_prefit",
        lambda *args: (SimpleNamespace(vector=seed.copy()), {"selected_path": "only102"}),
    )
    fresh_calls = []

    def fresh(obs, objective, prior, indices, prefit):
        assert objective is base
        np.testing.assert_array_equal(prefit.vector, seed)
        fresh_calls.append(True)
        return dict(status="qualified", calibration={"postfit": {"vector": seed.tolist()}})

    monkeypatch.setattr(driver, "fresh_calibration", fresh)
    downstream = []

    def continue_main():
        assert tmp_path == driver.continuation.HERE
        stage = next((tmp_path / "stages").glob("*.json"))
        receipt = json.loads(stage.read_text())
        assert receipt["key"] == "recovered-calibration"
        assert (
            receipt["value"]["result"]["diagnostics"]["source"]
            == "direct102 prefit; fresh103 correction/postfit"
        )
        downstream.append(True)
        driver.continuation.write(
            tmp_path / "result.json",
            dict(status="complete", protocol_sha256=receipt["protocol_sha256"]),
        )

    monkeypatch.setattr(driver.continuation, "main", continue_main)
    original_here = driver.continuation.HERE
    driver.main()
    assert fresh_calls == [True] and downstream == [True]
    assert original_here == driver.continuation.HERE
    driver.main()
    assert fresh_calls == [True] and downstream == [True]


def test_receiver_correction_failure_is_recorded(monkeypatch):
    prefit, base, *_ = setup(monkeypatch, converged=False)

    def fail(*args, **kwargs):
        raise ValueError("insufficient receiver support")

    monkeypatch.setattr(driver.continuation, "receiver_correction", fail)
    monkeypatch.setattr(
        driver.continuation,
        "fit_bounded_position",
        lambda *args, **kwargs: pytest.fail("No fit after bad correction"),
    )
    result = driver.fresh_calibration(object(), base, object(), [0, 1], prefit)
    assert result["status"] == "calibration-failed"
    assert "insufficient receiver support" in result["error"]
    assert result["calibration"] is None and result["postfit"] is None
