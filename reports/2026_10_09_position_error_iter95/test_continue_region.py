"""Synthetic controls for continuation selection and preserved regional receipts."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "continuation95", Path(__file__).with_name("continue_region.py")
)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


class FakeProblem:
    def __init__(self, objective, vector, **options):
        assert options == {"fixed_position": True, "slope_half_width_hz_s": 60}

    def feasible(self, vector):
        return vector[3] >= 0

    def stationarity(self, vector, gradient):
        return float(gradient[0])


class FakeObjective:
    def evaluate(self, vector):
        return (
            float(vector[2]),
            np.array([vector[4]]),
            SimpleNamespace(
                responsibilities=np.array([[0.5, 0.5]]), residual_hz=np.array([[2.0, 2.0]])
            ),
        )


def inventory(monkeypatch, rows):
    monkeypatch.setattr(driver, "_Problem", FakeProblem)
    monkeypatch.setattr(driver, "read", lambda path: rows[path.name])
    return {"prefit_inventory": [{"path": name, "fit_fields": ["fit"]} for name in rows]}


def receipt(score, *, converged=True, stationarity=0.0001, feasible=True, east=1.0):
    return {
        "fit": {
            "vector": [east, 2.0, score, float(feasible), stationarity],
            "objective": score,
            "converged": converged,
        }
    }


def test_only_independently_qualified_score_wins(monkeypatch):
    rows = {
        "solver-failed": receipt(1, converged=False),
        "gate-failed": receipt(2, stationarity=0.002),
        "infeasible": receipt(3, feasible=False),
        "winner": receipt(5),
        "qualified-worse": receipt(6),
    }
    # The fake feasible test uses a negative marker, independent of model score.
    rows["infeasible"]["fit"]["vector"][3] = -1
    result, audit = driver.select_prefit(
        inventory(monkeypatch, rows), FakeObjective(), np.array([1.0, 2.0])
    )
    assert result.objective == 5
    assert result.posterior_rms_hz == 2
    assert audit["selected_path"] == "winner"
    assert len(audit["inventory"]) == 5


def test_tie_breaks_by_path_not_insertion(monkeypatch):
    rows = {"z": receipt(5), "a": receipt(5)}
    _, audit = driver.select_prefit(
        inventory(monkeypatch, rows), FakeObjective(), np.array([1.0, 2.0])
    )
    assert audit["selected_path"] == "a"


@pytest.mark.parametrize("fault", ["point", "objective", "no-qualified"])
def test_reject_invalid_inventory(monkeypatch, fault):
    rows = {"entry": receipt(5)}
    if fault == "point":
        rows["entry"]["fit"]["vector"][0] = 99
    elif fault == "objective":
        rows["entry"]["fit"]["objective"] = 4
    else:
        rows["entry"]["fit"]["converged"] = False
    with pytest.raises((AssertionError, ValueError)):
        driver.select_prefit(inventory(monkeypatch, rows), FakeObjective(), np.array([1.0, 2.0]))


def test_ordinary_receipts_both_arms_all_starts_and_tamper():
    checkpoints = {}

    def add(suffix, result, reason=None):
        value = {"result": result, "reason": reason}
        checkpoints["prefix:point:test:" + suffix] = {
            "value": value,
            "value_sha256": driver.canonical_digest(value),
        }

    add("calibration", {"correction": {"knots_hz": [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]}})
    add("association", {"selected_indices": [2, 3], "selection": {"reference_free": True}})
    for arm in ("zero-c", "fitted-c"):
        for start in driver.Hard60Configuration().final_starts:
            add(arm + ":" + start, {"objective": 7, "converged": True})
    saved = {
        "regions": {
            "ordinary": {"prefix": "prefix", "basin": "point:test", "checkpoints": checkpoints}
        }
    }
    finals = driver.ordinary_regions(saved)["ordinary"]["finals"]
    assert len(finals) == 6
    assert {row["arm"] for row in finals} == {"zero-c", "fitted-c"}
    assert all(row["satellite_indices"] == [2, 3] for row in finals)
    assert all(row["calibration_penalty"] == pytest.approx(91 / 5000) for row in finals)
    checkpoints["prefix:point:test:association"]["value"]["result"]["selected_indices"] = [9]
    with pytest.raises(AssertionError):
        driver.ordinary_regions(saved)


def test_append_only_write(tmp_path):
    path = tmp_path / "receipt.json"
    driver.write(path, {"status": "first"})
    with pytest.raises(FileExistsError):
        driver.write(path, {"status": "replacement"})
    assert driver.read(path) == {"status": "first"}


def test_actual_driver_matched_finals_and_separate_baseline_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "HERE", tmp_path)
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    monkeypatch.setattr(driver, "PARENT", tmp_path)
    plan = dict(
        stage_fit_seconds=20,
        stage_iterations=600,
        association_seconds=60,
        slice_seconds=500,
        source_sha256={},
    )
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    (tmp_path / "published-v3.json").write_text(json.dumps({"manifest": {"document": {}}}))
    (tmp_path / "verified-checkpoints.json").write_text(
        json.dumps({"point_key": "point:1:2", "selected_basin": {"east_km": 1, "north_km": 2}})
    )
    (tmp_path / "ordinary-winner-checkpoints.json").write_text("{}")
    seed = np.arange(10, dtype=float)
    seed[:2] = [1, 2]
    seed[6] = 9
    bank = SimpleNamespace(numbers=np.array([111, 222]))
    bank.select = lambda indices: bank
    base = SimpleNamespace(
        bank=bank, design=np.zeros((2, 4)), evaluate=lambda vector: (0, 0, object())
    )
    monkeypatch.setattr(driver, "load_case", lambda *args: (object(), bank, object(), base, [0, 1]))
    prefit = SimpleNamespace(vector=seed.copy())
    monkeypatch.setattr(
        driver, "select_prefit", lambda *args: (prefit, {"selected_path": "synthetic"})
    )
    correction = SimpleNamespace(values_hz=np.zeros(2), knots_hz=np.zeros((2, 3)))
    monkeypatch.setattr(driver, "receiver_correction", lambda *args: correction)
    monkeypatch.setattr(driver, "Hard60Objective", lambda *args, **kwargs: base)
    monkeypatch.setattr(driver, "RegionalCalibration", lambda *args: {"synthetic": True})
    monkeypatch.setattr(
        driver,
        "_calibration",
        lambda value: SimpleNamespace(receiver_baseline_hz=np.zeros(2), correction=correction),
    )
    monkeypatch.setattr(
        driver,
        "associate_calibration",
        lambda *args, **kwargs: {
            "selected_indices": [0, 1],
            "initial_vector": seed.tolist(),
            "selection": {},
        },
    )
    fits = []

    def fit(objective, start, **options):
        fits.append((start.copy(), options))
        if options["rf_arm"] == "zero-c":
            start[6] = 0
        return driver.PositionFit(
            start.copy(), 5.0, 2.0, 10.0, 0.0001, True, False, "synthetic", 1, 0.001
        ), {}

    monkeypatch.setattr(driver, "fit_bounded_position", fit)
    monkeypatch.setattr(
        driver,
        "ordinary_regions",
        lambda saved: {"original": {"finals": [{"satellite_indices": [0, 1]}]}},
    )
    monkeypatch.setattr(driver, "regional_winners", lambda regions: {"regions": list(regions)})
    joint_calls = []

    def joint(observations, bank, prior, regions, stage):
        joint_calls.append(list(regions))
        result = stage("same-key", 90, lambda: {"region_count": len(regions)})
        return result["result"], [], []

    monkeypatch.setattr(driver, "run_joint_stages", joint)
    driver.main()
    result = driver.read(tmp_path / "result.json")
    assert result["status"] == "complete"
    assert result["baseline_operational"]["region_count"] == 1
    assert result["operational"]["region_count"] == 2
    assert len(fits) == 7  # One postfit plus three starts in each c arm.
    for _, options in fits:
        assert options["maximum_seconds"] == 20
        assert options["maximum_iterations"] == 600
        assert options["slope_half_width_hz_s"] == 60
    assert fits[0][1]["fixed_position"] is True
    for index in (2, 5):
        np.testing.assert_array_equal(fits[index][0][7:], 0)
    assert [row["arm"] for row in result["recovered_finals"]] == ["zero-c"] * 3 + ["fitted-c"] * 3
    assert all(row["fit"]["vector"][6] == 0 for row in result["recovered_finals"][:3])
    assert seed[6] == 9  # Shared association start was not mutated.
    driver.main()
    assert len(fits) == 7 and len(joint_calls) == 2
