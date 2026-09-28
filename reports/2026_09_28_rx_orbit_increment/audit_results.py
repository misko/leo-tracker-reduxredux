"""Independent receipt and arithmetic audit for the orbit-increment experiment."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import expit

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_causal_full_calibration import prepare_families
from tools.rx_joint_geometry_fit import BETA_SD, DIMENSIONS, calibration_score
from tools.rx_orbit_increment import _target_density, attach_orbit_increment

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TRAINING = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
MODEL = HERE / "model.json"
PRIOR_DS8 = ROOT / "reports/2026_09_28_rx_ds8_confirmation/results.json"
PANELS = {
    "pilot": (HERE / "pilot.json", TRAINING),
    "ds8": (HERE / "ds8.json", ROOT / "reports/2026_09_28_rx_ds8_confirmation/dataset.json"),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left, right, tolerance=1e-8):
    if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance):
        raise AssertionError(f"{left} != {right}")


def audit_model(model, training):
    prepared = prepare_families(training)
    rows = calibration_rows(training)
    ids = sorted(row["window_id"] for row in rows)
    assert model["training_dataset_sha256"] == sha256(TRAINING)
    assert model["training_source_window_ids"] == ids
    assert model["training_source_window_count"] == len(rows) == 1356
    assert model["calibration_sessions"] == sorted({row["session_id"] for row in rows})
    orbit, _ = attach_orbit_increment(prepared["uniform"])
    fits = []
    for arm, dimension in DIMENSIONS.items():
        candidates = model["fits"][arm]["candidates"]
        assert len(candidates) == 2 and all(row["success"] for row in candidates)
        for candidate in candidates:
            theta = np.asarray(candidate["parameters"], dtype=float)
            assert theta.shape == (dimension + 2,)
            score = calibration_score(
                orbit, theta[:dimension], float(expit(theta[-2])), math.exp(theta[-1])
            )
            penalty = 0.5 * float(np.sum((theta[:dimension] / BETA_SD[:dimension]) ** 2))
            penalty += 0.5 * (theta[-2] / 2.0) ** 2 + 0.5 * (theta[-1] / 1.5) ** 2
            close(score, candidate["calibration_relative_log_evidence"])
            close(penalty, candidate["map_penalty"])
            close(score - penalty, candidate["map_gain"])
        best = max(candidates, key=lambda row: row["map_gain"])
        selected = model["fits"][arm]["selected"]
        close(selected["map_gain"], best["map_gain"])
        np.testing.assert_allclose(selected["beta"], best["parameters"][:dimension], atol=1e-12)
        fits.append({"arm": arm, "converged_starts": 2, "map_gain": selected["map_gain"]})
    return fits


def value(record, family, name, role):
    return record[family][name]["roles"][role]["relative_log_score_per_window"]


def audit_panel(name, result, dataset):
    assert result["status"] == "complete" and len(result["evaluation_sessions"]) == 4
    expected_ids = sorted(
        {
            lane["lane"]["session_id"]
            for lane in dataset["lanes"]
            if lane["recording_split"] == "evaluation"
        }
    )
    assert result["evaluation_sessions"] == expected_ids
    assert result["coverage"]["lanes"] == sum(
        lane["recording_split"] == "evaluation" for lane in dataset["lanes"]
    )
    assert result["source_sha256"]["dataset"] == sha256(PANELS[name][1])
    role_checks = 0
    for record in result["records"].values():
        references = {}
        for family in ("orbit_increment", "static_causal"):
            for evaluation in record[family].values():
                for role in ("reception", "held_frequency"):
                    rows = [
                        window
                        for lane in evaluation["lanes"]
                        for window in lane["windows"]
                        if window["role"] == role
                    ]
                    total = evaluation["roles"][role]
                    assert len(rows) == total["windows"]
                    relative = math.fsum(row["relative_log_score"] for row in rows)
                    reference = math.fsum(row["reference_log_score"] for row in rows)
                    close(relative, total["relative_log_score"])
                    close(reference, total["reference_log_score"])
                    close(relative + reference, total["full_log_score"])
                    key = role
                    if key in references:
                        close(reference, references[key], 1e-10)
                    else:
                        references[key] = reference
                    role_checks += 1
    # Every aggregate is reconstructed from its record-level operands.
    for key, aggregate in result["aggregate_equal_record"].items():
        role, expression = key.split(":", 1)
        values = {}
        for sid, record in result["records"].items():
            if expression.endswith("-causal_reference"):
                left = expression[: -len("-causal_reference")]
                if left.startswith("orbit_increment_"):
                    family, component = "orbit_increment", left[len("orbit_increment_") :]
                else:
                    assert left.startswith("static_causal_")
                    family, component = "static_causal", left[len("static_causal_") :]
                values[sid] = value(record, family, component, role)
            elif expression.startswith("orbit_increment_") and "-static_causal_" in expression:
                left, right = expression.split("-static_causal_")
                component = left[len("orbit_increment_") :]
                assert component == right
                values[sid] = value(record, "orbit_increment", component, role) - value(
                    record, "static_causal", component, role
                )
            else:
                left, right = expression[len("orbit_increment_") :].split("-")
                values[sid] = value(record, "orbit_increment", left, role) - value(
                    record, "orbit_increment", right, role
                )
        assert values.keys() == aggregate["records"].keys()
        for sid, observed in values.items():
            close(observed, aggregate["records"][sid], 1e-12)
        close(math.fsum(values.values()) / len(values), aggregate["equal_record_mean"], 1e-12)
        assert sum(v > 0 for v in values.values()) == aggregate["positive_records"]
    # Diagnostic histories are strictly earlier; normalized targets integrate to one.
    history_checks = 0
    density_checks = 0
    source_times = {
        window["source_window_id"]: window["prediction_utc_ns"]
        for lane in dataset["lanes"]
        for window in lane["windows"]
    }
    periods = {
        tuple(lane["lane"][key] for key in ("session_id", "channel", "edge", "actual_rf_hz")):
        lane["alias_period_hz"]
        for lane in dataset["lanes"]
    }
    for receipts in result["orbit_increment_diagnostics"].values():
        for lane in receipts:
            lane_key = tuple(
                lane["lane"][key] for key in ("session_id", "channel", "edge", "actual_rf_hz")
            )
            period = periods[lane_key]
            for receiver in lane["receivers"]:
                prior_times = {}
                for window in receiver["windows"]:
                    current = source_times[window["source_window_id"]]
                    for nominee in window["nominees"]:
                        history_id = nominee["history_source_window_id"]
                        if history_id is not None:
                            assert prior_times[history_id] < current
                            history_checks += 1
                        if density_checks < 100:
                            grid = np.linspace(0.0, 1.0, 20001) * period
                            density = _target_density(
                                grid, nominee["target_means_hz"], nominee["sigma_hz"], period
                            )
                            close(np.trapezoid(density, grid / period), 1.0, 2e-7)
                            density_checks += 1
                    prior_times[window["source_window_id"]] = current
    assert history_checks > 0
    return {
        "role_totals": role_checks,
        "causal_history_links": history_checks,
        "density_normalization_checks": density_checks,
    }


def main():
    training = json.loads(TRAINING.read_text())
    model = json.loads(MODEL.read_text())
    fit_checks = audit_model(model, training)
    panels = {}
    for name, (result_path, dataset_path) in PANELS.items():
        panels[name] = audit_panel(
            name, json.loads(result_path.read_text()), json.loads(dataset_path.read_text())
        )
    prior_ds8 = json.loads(PRIOR_DS8.read_text())
    current_ds8 = json.loads(PANELS["ds8"][0].read_text())
    for sid, record in current_ds8["records"].items():
        for arm in DIMENSIONS:
            assert record["static_causal"][arm] == prior_ds8["records"][sid]["families"][
                "causal"
            ]["evaluations"][arm]
    panels["ds8"]["static_replay_exact_prior_result"] = True
    paths = [MODEL, TRAINING, PRIOR_DS8, Path(__file__)] + [
        path for pair in PANELS.values() for path in pair
    ]
    result = {
        "schema": "rx-orbit-increment-audit/v1",
        "status": "pass",
        "fit_checks": fit_checks,
        "panels": panels,
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in paths},
    }
    with (HERE / "audit-results.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
