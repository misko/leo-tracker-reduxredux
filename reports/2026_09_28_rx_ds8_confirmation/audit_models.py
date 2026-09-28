"""Independently replay the frozen full-calibration model receipts."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from scipy.special import expit

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_causal_full_calibration import full_reception_scaler, prepare_families
from tools.rx_empirical_background import fit
from tools.rx_joint_geometry_fit import BETA_SD, DIMENSIONS, calibration_score

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
MODEL = HERE / "models.json"
DATASET = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def close(left, right, tolerance=1e-8):
    if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance):
        raise AssertionError(f"{left} != {right}")


def main():
    model = json.loads(MODEL.read_text())
    document = json.loads(DATASET.read_text())
    prepared = prepare_families(document)
    rows = calibration_rows(document)
    window_ids = sorted(row["window_id"] for row in rows)
    sessions = sorted({row["session_id"] for row in rows})
    assert model["dataset_sha256"] == sha256(DATASET)
    assert model["calibration_sessions"] == sessions and len(sessions) == 6
    assert model["training_source_window_ids"] == window_ids
    assert model["training_source_window_count"] == len(rows)
    assert model["training_source_window_ids_sha256"] == canonical_hash(window_ids)
    background = fit(rows, "joint")
    assert model["background_model"] == background
    assert model["background_model_sha256"] == canonical_hash(background)
    center, scale = full_reception_scaler(document)
    np.testing.assert_allclose(model["feature_center"], center, rtol=0, atol=1e-12)
    np.testing.assert_allclose(model["feature_scale"], scale, rtol=0, atol=1e-12)

    checks = []
    for family in ("uniform", "causal"):
        lanes = prepared[family]
        assert sum(len(lane["times"]) for lane in lanes) == len(rows)
        assert {lane["source"]["lane"]["session_id"] for lane in lanes} == set(sessions)
        for arm, dimension in DIMENSIONS.items():
            fitted = model["families"][family]["fits"][arm]
            candidates = fitted["candidates"]
            assert len(candidates) == 2
            converged = []
            for candidate in candidates:
                parameters = np.asarray(candidate["parameters"], dtype=float)
                assert parameters.shape == (dimension + 2,)
                beta = parameters[:dimension]
                occupancy = float(expit(parameters[-2]))
                tau = math.exp(parameters[-1])
                score = calibration_score(lanes, beta, occupancy, tau)
                penalty = 0.5 * float(np.sum((beta / BETA_SD[:dimension]) ** 2))
                penalty += 0.5 * (parameters[-2] / 2.0) ** 2
                penalty += 0.5 * (parameters[-1] / 1.5) ** 2
                close(score, candidate["calibration_relative_log_evidence"])
                close(penalty, candidate["map_penalty"])
                close(score - penalty, candidate["map_gain"])
                if candidate["success"]:
                    converged.append(candidate)
            assert converged
            best = max(converged, key=lambda row: row["map_gain"])
            selected = fitted["selected"]
            assert selected["null_selected"] is (best["map_gain"] <= 0)
            if not selected["null_selected"]:
                np.testing.assert_allclose(
                    selected["beta"], best["parameters"][:dimension], rtol=0, atol=1e-12
                )
                close(selected["occupancy"], expit(best["parameters"][-2]), 1e-12)
                close(selected["tau_s"], math.exp(best["parameters"][-1]), 1e-12)
                for key in (
                    "calibration_relative_log_evidence",
                    "map_penalty",
                    "map_gain",
                ):
                    close(selected[key], best[key])
            checks.append(
                {
                    "family": family,
                    "arm": arm,
                    "dimension": dimension,
                    "converged_starts": sum(row["success"] for row in candidates),
                    "selected_map_gain": selected["map_gain"],
                    "selected_null": selected["null_selected"],
                }
            )
    result = {
        "schema": "rx-ds8-model-audit/v1",
        "status": "pass",
        "training_sessions": sessions,
        "training_windows": len(rows),
        "fits": checks,
        "source_sha256": {
            str(MODEL.relative_to(ROOT)): sha256(MODEL),
            str(DATASET.relative_to(ROOT)): sha256(DATASET),
            str(Path(__file__).relative_to(ROOT)): sha256(Path(__file__)),
        },
    }
    output = HERE / "audit-models.json"
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
