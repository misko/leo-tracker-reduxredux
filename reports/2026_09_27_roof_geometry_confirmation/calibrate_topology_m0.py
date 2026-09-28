"""Direction-free M0 reception control on the audited calibration population."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
sys.path[:0] = [str(HERE), str(DIRECTION)]
import calibrate_topology_reception as topology
import model_eval


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def fit_m0(
    model_rows: list[dict], audit: dict, calibration_sessions: set[str],
) -> dict[str, object]:
    retained, accounting = topology.topology_filtered_rows(
        model_rows, audit, calibration_sessions
    )
    detection_models = model_eval.fit_detection_models(retained, ridge=1.0)
    ratio_models = model_eval.fit_continuous_models(retained, ridge=1.0)
    detection = detection_models["M0"]
    ratio = ratio_models["M0"]
    matched = [row for row in retained
               if row["log_margin_ratio_rx1_rx0"] is not None]
    residual = (np.asarray([float(row["log_margin_ratio_rx1_rx0"])
                            for row in matched])
                - model_eval.predict(ratio, matched))
    weights = np.asarray(model_eval.track_weights(matched))
    variance = float(np.sum(weights * residual**2) / np.sum(weights))
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError("invalid M0 ratio variance")
    if detection.direction or ratio.direction:
        raise ValueError("M0 control unexpectedly contains direction")
    return {
        "detection": asdict(detection),
        "ratio": asdict(ratio),
        "ratio_variance": variance,
        "ridge": 1.0,
        "calibration_sessions": sorted(calibration_sessions),
        "filter_accounting": accounting,
        "calibration_metrics": {
            "detection": model_eval.score_models(detection_models, retained),
            "continuous_ratio": model_eval.score_models(ratio_models, matched),
        },
        "control": (
            "Direction-free reception likelihood. Candidate/location-invariant "
            "within each fixed track; scored through the same shared-identity "
            "marginalization and full reserve denominator as M1."
        ),
    }


def main() -> None:
    target = HERE / "topology_m0_calibration.json"
    if target.exists():
        raise FileExistsError("topology M0 calibration is frozen")
    audit_path = HERE / "audit_source_topology.json"
    rows_path = DIRECTION / "model_rows.json"
    inventory_path = DIRECTION / "evaluation_inventory.json"
    confirmation_inventory_path = HERE / "inventory.json"
    audit_bytes = audit_path.read_bytes()
    rows_bytes = rows_path.read_bytes()
    source_inventory = json.loads(inventory_path.read_text())
    calibration_sessions = {
        row["session_id"] for row in source_inventory
        if row["split"] == "calibration"
    }
    if len(calibration_sessions) != 6:
        raise ValueError("expected six frozen calibration sessions")
    output = fit_m0(
        json.loads(rows_bytes), json.loads(audit_bytes), calibration_sessions
    )
    confirmation_inventory = json.loads(confirmation_inventory_path.read_text())
    calibration_rates = sorted({
        int(row["sample_rate_hz"]) for row in source_inventory
        if row["session_id"] in calibration_sessions
    })
    confirmation_rates = sorted({int(row["sample_rate_hz"])
                                 for row in confirmation_inventory})
    output.update({
        "scope": "six audited calibration scans only; no development or confirmation outcomes",
        "topology_audit_sha256": digest(audit_bytes),
        "source_model_rows_sha256": digest(rows_bytes),
        "source_inventory_sha256": digest(inventory_path.read_bytes()),
        "confirmation_inventory_sha256": digest(confirmation_inventory_path.read_bytes()),
        "model_eval_sha256": digest((DIRECTION / "model_eval.py").read_bytes()),
        "topology_filter_code_sha256": digest((HERE / "calibrate_topology_reception.py").read_bytes()),
        "code_sha256": digest(Path(__file__).read_bytes()),
        "calibration_sample_rate_hz": calibration_rates,
        "confirmation_sample_rate_hz": confirmation_rates,
        "unseen_confirmation_sample_rate_hz": sorted(
            set(confirmation_rates) - set(calibration_rates)
        ),
        "unseen_rate_policy": (
            "model_eval reference-level encoding: a sample rate absent from "
            "calibration receives no fitted sample-rate dummy coefficient"
        ),
    })
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    temporary.replace(target)


if __name__ == "__main__":
    main()
