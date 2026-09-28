"""Topology-filtered reception calibration using only the frozen six scans."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
sys.path.insert(0, str(DIRECTION))
import model_eval


def digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def topology_filtered_rows(
    model_rows: list[dict], audit: dict, calibration_sessions: set[str],
) -> tuple[list[dict], dict[str, object]]:
    sessions = audit.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != len(calibration_sessions) + 4:
        raise ValueError("source-topology audit is incomplete")
    audit_cal = {row["session_id"]: row for row in sessions if row["split"] == "calibration"}
    audit_fresh = [row for row in sessions if row["split"] == "confirmation"]
    if set(audit_cal) != calibration_sessions or len(audit_fresh) != 4:
        raise ValueError("source-topology audit cohort mismatch")
    removed = {
        (sid, track_id)
        for sid, session in audit_cal.items()
        for track_id in session["removed_track_ids"]
    }
    calibration = [row for row in model_rows if row["split"] == "cal"]
    if {row["session_id"] for row in calibration} != calibration_sessions:
        raise ValueError("model-row calibration cohort mismatch")
    retained = [dict(row) for row in calibration
                if (row["session_id"], row["track_id"]) not in removed]
    present_tracks = {(row["session_id"], row["track_id"]) for row in calibration}
    absent = sorted(removed - present_tracks)
    if absent:
        raise ValueError("audit removes calibration tracks absent from model rows")
    if not retained:
        raise ValueError("topology filter removes all calibration rows")
    removed_rows = len(calibration) - len(retained)
    accounting = {
        "input_calibration_rows": len(calibration),
        "retained_calibration_rows": len(retained),
        "removed_calibration_rows": removed_rows,
        "input_calibration_tracks": len(present_tracks),
        "retained_calibration_tracks": len({
            (row["session_id"], row["track_id"]) for row in retained
        }),
        "removed_calibration_tracks": len(removed),
        "removed_track_ids_by_session": {
            sid: list(audit_cal[sid]["removed_track_ids"])
            for sid in sorted(audit_cal)
        },
    }
    return retained, accounting


def fit_calibration(
    model_rows: list[dict], audit: dict, calibration_sessions: set[str],
) -> dict[str, object]:
    retained, accounting = topology_filtered_rows(
        model_rows, audit, calibration_sessions
    )
    detection_models = model_eval.fit_detection_models(retained, ridge=1.0)
    ratio_models = model_eval.fit_continuous_models(retained, ridge=1.0)
    detection = detection_models["M1"]
    ratio = ratio_models["M1"]
    matched = [row for row in retained
               if row["log_margin_ratio_rx1_rx0"] is not None]
    residual = (np.asarray([float(row["log_margin_ratio_rx1_rx0"]) for row in matched])
                - model_eval.predict(ratio, matched))
    weights = np.asarray(model_eval.track_weights(matched))
    variance = float(np.sum(weights * residual**2) / np.sum(weights))
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError("invalid topology-filtered ratio variance")
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
        "feature_method": (
            "Unchanged original known-site, Gaussian-association-derived direction "
            "features and M1 model definitions; only whole source-collision tracks "
            "are removed before refitting."
        ),
        "limitation": (
            "Direction features are the original Gaussian top-three known-site "
            "features, not directions rederived from the later robust Student-t "
            "association. This preserves the frozen feature method but is a modular "
            "model limitation, not a robust-angle calibration claim."
        ),
    }


def main() -> None:
    target = HERE / "topology_calibration.json"
    if target.exists():
        raise FileExistsError("topology reception calibration is frozen")
    audit_path = HERE / "audit_source_topology.json"
    rows_path = DIRECTION / "model_rows.json"
    inventory_path = DIRECTION / "evaluation_inventory.json"
    results_path = DIRECTION / "results.json"
    pairing_path = DIRECTION / "pairing_summary.json"
    audit_bytes = audit_path.read_bytes()
    rows_bytes = rows_path.read_bytes()
    audit = json.loads(audit_bytes)
    model_rows = json.loads(rows_bytes)
    inventory = json.loads(inventory_path.read_text())
    calibration_sessions = {
        row["session_id"] for row in inventory if row["split"] == "calibration"
    }
    if len(calibration_sessions) != 6:
        raise ValueError("expected the frozen six calibration scans")
    output = fit_calibration(model_rows, audit, calibration_sessions)
    output.update({
        "scope": "six frozen calibration scans only; no development or confirmation rows",
        "source_model_rows_sha256": digest(rows_bytes),
        "source_results_sha256": digest(results_path.read_bytes()),
        "topology_audit_sha256": digest(audit_bytes),
        "pairing_summary_sha256": digest(pairing_path.read_bytes()),
        "source_inventory_sha256": digest(inventory_path.read_bytes()),
        "model_eval_sha256": digest((DIRECTION / "model_eval.py").read_bytes()),
        "code_sha256": digest(Path(__file__).read_bytes()),
    })
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    temporary.replace(target)


if __name__ == "__main__":
    main()
