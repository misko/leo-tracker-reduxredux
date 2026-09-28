from dataclasses import asdict
import importlib.util
from pathlib import Path
import sys

import pytest


PATH = Path(__file__).with_name("run_consistent_replay.py")
SPEC = importlib.util.spec_from_file_location("run_consistent_replay", PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def model(outcome="detection"):
    return RUNNER.base.model_eval.FittedModel(
        outcome=outcome, direction=True, feature_names=("intercept",),
        channel_levels=("1",), edge_levels=("lower",),
        channel_edge_levels=("1:lower",), sample_rate_levels=("1",),
        numeric_names=(), means=(), scales=(), coefficients=(0.,))


def calibration():
    detection = model()
    ratio = model("continuous")
    return {
        "old": {"detection": {"M1": asdict(detection)},
                "ratio": {"M1": asdict(ratio)},
                "ratio_variance": {"M1": 2.}},
        "consistent": {"detection": {"M1": asdict(detection)},
                       "ratio": {"M1": asdict(ratio)},
                       "ratio_variance": {"M1": 3.}},
        "source_hashes": {}, "calibration_sessions": ["s"],
        "join_accounting": {"exact_join_rows": 6378},
        "m0_invariance": {"detection_model_exact": True,
                          "ratio_model_exact": True,
                          "ratio_variance_exact": True},
    }


def test_calibration_gate_accepts_exact_old_and_rejects_drift():
    detection = model(); ratio = model("continuous")
    _, _, variance = RUNNER.validate_calibration(
        calibration(), detection, ratio, 2.)
    assert variance == 3.
    changed = calibration(); changed["old"]["ratio_variance"]["M1"] = 2.1
    with pytest.raises(ValueError, match="variance differs"):
        RUNNER.validate_calibration(changed, detection, ratio, 2.)
    rounded = calibration()
    rounded["old"]["detection"]["M1"]["coefficients"] = [5e-13]
    RUNNER.validate_calibration(rounded, detection, ratio, 2.)
    rounded["old"]["detection"]["M1"]["coefficients"] = [2e-12]
    with pytest.raises(ValueError, match="coefficients differ"):
        RUNNER.validate_calibration(rounded, detection, ratio, 2.)
    metadata = calibration()
    metadata["old"]["ratio"]["M1"]["outcome"] = "detection"
    with pytest.raises(ValueError, match="metadata differs"):
        RUNNER.validate_calibration(metadata, detection, ratio, 2.)


def saved_branch():
    return {"grid_count": 2, "point_components": [
        {"east_km": 0., "north_km": 0., "scores": {"D": 1., "D_plus_geometry": 2.}},
        {"east_km": 1., "north_km": 0., "scores": {"D": 3., "D_plus_geometry": 4.}},
    ]}


def replay(delta=0., d_delta=0.):
    return [
        {"east_km": 0., "north_km": 0., "variant_scores": {
            "old": {"D": 1. + delta, "D_plus_geometry": 2.},
            "consistent": {"D": 1. + delta + d_delta, "D_plus_geometry": 1.5}}},
        {"east_km": 1., "north_km": 0., "variant_scores": {
            "old": {"D": 3., "D_plus_geometry": 4.},
            "consistent": {"D": 3., "D_plus_geometry": 4.5}}},
    ]


def test_parity_gate_checks_every_point_and_d_invariance():
    report = RUNNER.parity_report(saved_branch(), replay(delta=5e-8))
    assert report["passed"] and report["points"] == 2
    with pytest.raises(ValueError, match="parity failed"):
        RUNNER.parity_report(saved_branch(), replay(delta=2e-7))
    with pytest.raises(ValueError, match="changed D"):
        RUNNER.parity_report(saved_branch(), replay(d_delta=1e-9))
    nonfinite = replay()
    nonfinite[1]["variant_scores"]["old"]["D_plus_geometry"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        RUNNER.parity_report(saved_branch(), nonfinite)


def test_grid_and_report_gates_reject_duplicates_or_missing_points():
    duplicate = saved_branch()
    duplicate["point_components"][1]["east_km"] = 0.
    with pytest.raises(ValueError, match="duplicated"):
        RUNNER.grid_points(duplicate)
    with pytest.raises(ValueError, match="inventory differs"):
        RUNNER.parity_report(saved_branch(), replay()[:1])


def test_selection_is_deterministic_and_variant_specific():
    rows = replay()
    assert RUNNER.select_min(rows, "consistent", "D_plus_geometry")["east_km"] == 0.
