"""Calibration-only reception refit with robust-association mean directions."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
CONFIRMATION = HERE.parent / "2026_09_27_roof_geometry_confirmation"
sys.path[:0] = [str(DIRECTION), str(CONFIRMATION)]
import model_eval
from calibrate_topology_reception import topology_filtered_rows


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def replace_directions(rows: list[dict], directions: list[dict]) -> list[dict]:
    keys = [(row["session_id"], row["track_id"], row["observation_id"])
            for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate retained model-row join key")
    direction_keys = [(row["session_id"], row["track_id"], row["observation_id"])
                      for row in directions]
    if len(direction_keys) != len(set(direction_keys)):
        raise ValueError("duplicate direction join key")
    if set(keys) != set(direction_keys):
        missing = set(keys) - set(direction_keys)
        unexpected = set(direction_keys) - set(keys)
        raise ValueError(f"direction join mismatch: missing={len(missing)} unexpected={len(unexpected)}")
    lookup = {key: row for key, row in zip(direction_keys, directions, strict=True)}
    result = []
    for key, row in zip(keys, rows, strict=True):
        direction = lookup[key]
        changed = dict(row)
        changed["east"] = float(direction["robust_mean_east"])
        changed["up"] = float(direction["robust_mean_up"])
        result.append(changed)
    return result


def ratio_variance(model: model_eval.FittedModel, rows: list[dict]) -> float:
    matched = [row for row in rows if row["log_margin_ratio_rx1_rx0"] is not None]
    residual = (np.asarray([float(row["log_margin_ratio_rx1_rx0"]) for row in matched])
                - model_eval.predict(model, matched))
    weights = np.asarray(model_eval.track_weights(matched))
    value = float(np.sum(weights * residual**2) / np.sum(weights))
    if not np.isfinite(value) or value <= 0:
        raise ValueError("invalid ratio variance")
    return value


def fit_bundle(rows: list[dict]) -> dict:
    detection = model_eval.fit_detection_models(rows, ridge=1.0)
    ratio = model_eval.fit_continuous_models(rows, ridge=1.0)
    matched = [row for row in rows if row["log_margin_ratio_rx1_rx0"] is not None]
    return {
        "detection": {name: asdict(model) for name, model in detection.items()},
        "ratio": {name: asdict(model) for name, model in ratio.items()},
        "ratio_variance": {name: ratio_variance(model, rows)
                           for name, model in ratio.items()},
        "metrics": {
            "detection": model_eval.score_models(detection, rows),
            "conditional_ratio": model_eval.score_models(ratio, matched),
        },
    }


def conditional_loso(old_rows: list[dict], new_rows: list[dict]) -> list[dict]:
    sessions = sorted({row["session_id"] for row in old_rows})
    result = []
    for held in sessions:
        conventions = {}
        for name, source in (("old", old_rows), ("consistent", new_rows)):
            train = [dict(row) for row in source if row["session_id"] != held]
            test = [dict(row, split="holdout") for row in source if row["session_id"] == held]
            detection = model_eval.fit_detection_models(train, ridge=1.0)
            ratio = model_eval.fit_continuous_models(train, ridge=1.0)
            conventions[name] = {
                "detection": model_eval.score_models(detection, test),
                "conditional_ratio": model_eval.score_models(
                    ratio, [row for row in test
                            if row["log_margin_ratio_rx1_rx0"] is not None]),
            }
        result.append({
            "held_session": held,
            "training_sessions": [sid for sid in sessions if sid != held],
            "old": conventions["old"], "consistent": conventions["consistent"],
            "caveat": "Reception fit excludes this scan, but robust frequency parameters, identities, and weights were estimated using all six calibration scans; this is conditional LOSO, not nested frequency validation.",
        })
    return result


def _coefficients(bundle: dict, outcome: str, name: str) -> np.ndarray:
    return np.asarray(bundle[outcome][name]["coefficients"], float)


def main() -> None:
    target = HERE / "calibration_consistent_calibration.json"
    if target.exists():
        raise FileExistsError(f"refusing to overwrite {target}")
    rows_path = DIRECTION / "model_rows.json"
    audit_path = CONFIRMATION / "audit_source_topology.json"
    directions_path = HERE / "calibration_directions_data.json"
    protocol_path = HERE / "CONSISTENT_CALIBRATION_PROTOCOL.md"
    inventory_path = DIRECTION / "evaluation_inventory.json"
    rows_bytes = rows_path.read_bytes()
    audit_bytes = audit_path.read_bytes()
    direction_bytes = directions_path.read_bytes()
    model_rows = json.loads(rows_bytes)
    audit = json.loads(audit_bytes)
    direction_data = json.loads(direction_bytes)
    sessions = {row["session_id"] for row in json.loads(inventory_path.read_text())
                if row["split"] == "calibration"}
    if len(sessions) != 6:
        raise ValueError("expected six frozen calibration sessions")
    retained, accounting = topology_filtered_rows(model_rows, audit, sessions)
    consistent = replace_directions(retained, direction_data["rows"])
    old = fit_bundle(retained)
    new = fit_bundle(consistent)
    for outcome in ("detection", "ratio"):
        if old[outcome]["M0"] != new[outcome]["M0"]:
            raise ValueError(f"{outcome} M0 changed under direction-only substitution")
    if old["ratio_variance"]["M0"] != new["ratio_variance"]["M0"]:
        raise ValueError("M0 ratio variance changed under direction-only substitution")

    changes = {}
    for outcome in ("detection", "ratio"):
        before = _coefficients(old, outcome, "M1")
        after = _coefficients(new, outcome, "M1")
        changes[outcome] = {
            "feature_names": old[outcome]["M1"]["feature_names"],
            "old_coefficients": before.tolist(),
            "consistent_coefficients": after.tolist(),
            "coefficient_delta": (after - before).tolist(),
            "coefficient_l2_change": float(np.linalg.norm(after - before)),
            "old_equal_track_loss": old["metrics"][
                "detection" if outcome == "detection" else "conditional_ratio"
            ]["equal_track"]["M1"],
            "consistent_equal_track_loss": new["metrics"][
                "detection" if outcome == "detection" else "conditional_ratio"
            ]["equal_track"]["M1"],
        }
    changes["ratio_variance_M1"] = {
        "old": old["ratio_variance"]["M1"],
        "consistent": new["ratio_variance"]["M1"],
        "delta": new["ratio_variance"]["M1"] - old["ratio_variance"]["M1"],
    }
    output = {
        "scope": "Six frozen, topology-retained calibration scans only; exact robust mean-direction substitution; no evaluation outcomes, frequency refit, or geographic search.",
        "ridge": 1.0, "calibration_sessions": sorted(sessions),
        "join_accounting": {**accounting, "direction_rows": len(direction_data["rows"]),
                            "exact_join_rows": len(consistent)},
        "source_hashes": {
            "model_rows": digest(rows_bytes), "topology_audit": digest(audit_bytes),
            "calibration_directions_data": digest(direction_bytes),
            "consistent_protocol": digest(protocol_path.read_bytes()),
            "evaluation_inventory": digest(inventory_path.read_bytes()),
            "model_eval": digest((DIRECTION / "model_eval.py").read_bytes()),
            "fit_code": digest(Path(__file__).read_bytes()),
        },
        "old": old, "consistent": new, "changes": changes,
        "m0_invariance": {"detection_model_exact": True, "ratio_model_exact": True,
                          "ratio_variance_exact": True},
        "conditional_loso": conditional_loso(retained, consistent),
        "feature_method": "Identical M0/M1 design, ridge=1, nuisance fields, outcomes, and unit-total-per-track weighting; only east/up are replaced by robust-top3 weighted means joined by session/track/observation ID.",
        "limitation": "Reception training still uses a marginalized direction feature while geographic scoring marginalizes candidate likelihoods. LOSO reception results condition on frequency parameters and associations fitted to all six scans and are not fully nested out-of-sample validation.",
    }
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    temporary.replace(target)


if __name__ == "__main__":
    main()
