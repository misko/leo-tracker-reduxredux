"""Topology-filtered calibration-only Student-t fixed-point refit."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
DIRECTION = HERE.parent / "2026_09_27_roof_direction_subset"
CONFIRMATION = HERE.parent / "2026_09_27_roof_geometry_confirmation"
sys.path[:0] = [str(HERE), str(DIRECTION), str(CONFIRMATION)]

import calibrate_frequency_fixedpoint as fixedpoint
from fit_frequency import fit
from source_links import resolve
from source_topology import filter_prepared
from leo.analysis.adaptive_tle_prediction import RegionalTrackPredictionEvaluator, build_prediction_banks
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader


INITIAL = (132.45056967671437, 1.585959259734901)
MAX_ROUNDS = 5


def main() -> None:
    extraction_path = HERE / "topology_frequency_fixedpoint.json"
    parameters_path = HERE / "topology_frequency_parameters.json"
    if extraction_path.exists() or parameters_path.exists():
        raise FileExistsError("topology frequency artifacts exist; refusing overwrite")
    started = time.monotonic()
    audit_path = CONFIRMATION / "audit_source_topology.json"
    audit_bytes = audit_path.read_bytes()
    audit = json.loads(audit_bytes)
    if audit.get("calibration_zero_excluded"):
        raise ValueError("topology refit requires measured calibration exclusions")
    audit_rows = {row["session_id"]: row for row in audit["sessions"]
                  if row["split"] == "calibration"}
    inventory = {row["session_id"]: row for row in
                 json.loads((DIRECTION / "evaluation_inventory.json").read_text())}
    frozen = json.loads((HERE / "fixedpoint_parameters.json").read_text())
    if sorted(audit_rows) != frozen["calibration_sessions"]:
        raise ValueError("topology audit does not cover the frozen calibration cohort")
    if audit["source_code_sha256"]["source_topology.py"] != fixedpoint.digest(
            (CONFIRMATION / "source_topology.py").read_bytes()):
        raise ValueError("topology implementation changed after audit")
    if audit["source_code_sha256"]["source_links.py"] != fixedpoint.digest(
            (DIRECTION / "source_links.py").read_bytes()):
        raise ValueError("source-link implementation changed after audit")

    cache = {}
    source_digests = {}
    for sid in frozen["calibration_sessions"]:
        entry = inventory[sid]
        audit_row = audit_rows[sid]
        payload = Path(entry["cache_file"]).read_bytes()
        if (not entry["ready"] or entry["split"] != "calibration" or
                fixedpoint.digest(payload) != entry["cache_sha256"]):
            raise ValueError(f"{sid}: invalid calibration cache")
        raw = pickle.loads(payload)
        prepared = prepare_adaptive_tle_position_inputs(
            sid, inputs=fixedpoint.CachedInput(raw),
            archive=TleArchiveReader(Path("/var/lib/leo/tle")))
        if (prepared.input_manifest_sha256 != entry["input_manifest_sha256"] or
                prepared.analysis_manifest_sha256 != entry["analysis_manifest_sha256"]):
            raise ValueError(f"{sid}: prepared digest mismatch")
        for key in ("input_manifest_sha256", "analysis_manifest_sha256",
                    "evidence_sha256", "snapshot_digest"):
            if getattr(prepared, key) != audit_row[key]:
                raise ValueError(f"{sid}: prepared source differs from topology audit")
        links = resolve(raw)
        if fixedpoint.digest(json.dumps(
                links, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
                ) != audit_row["source_links_sha256"]:
            raise ValueError(f"{sid}: source links differ from topology audit")
        filtered, receipt = filter_prepared(prepared, links)
        if (receipt["removed_track_ids"] != audit_row["removed_track_ids"] or
                receipt["counts"] != audit_row["counts"] or
                receipt["unchanged"] != audit_row["unchanged"]):
            raise ValueError(f"{sid}: topology receipt differs from frozen audit")

        # Build the full public bank first, then retain only whole tracks allowed
        # by the frozen provenance-only topology receipt.
        banks, prediction_receipt = build_prediction_banks(
            prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns,
            prepared.tracks, taus_s=np.array([0.]))
        pose = next(item["pose"]["pose_authority"] for item in
                    json.loads((DIRECTION / "evaluation_manifest.json").read_text())["sessions"]
                    if item["pose"]["session_id"] == sid)
        blocks = defaultdict(list)
        evaluator = RegionalTrackPredictionEvaluator(
            banks,
            lambda east, north, lat=pose["latitude_deg"], lon=pose["longitude_deg"]:
                fixedpoint.point(lat, lon),
            taus_s=np.array([0.]))
        for block in evaluator(0, 0):
            blocks[block.track_id].append(block)
        retained_ids = {track.track_id for track in filtered.tracks}
        rows = []
        for track in prepared.tracks:
            if track.track_id not in retained_ids:
                continue
            chunks = blocks[track.track_id]
            predicted = np.concatenate([chunk.predictions_hz[:, 0, :] for chunk in chunks])
            candidate_ids = np.concatenate([chunk.candidate_ids for chunk in chunks])
            visible = np.concatenate([np.asarray(chunk.visible).reshape(-1) for chunk in chunks])
            keep = np.flatnonzero(visible)
            if not len(keep):
                raise ValueError(f"{sid}/{track.track_id}: no visible candidates")
            rows.append({
                "track_id": track.track_id,
                "candidate_ids": candidate_ids[keep].astype(int),
                "predicted_hz": predicted[keep].astype(np.float64),
                "measured_hz": np.asarray(track.measured_hz, float),
                "training_mask": np.asarray(track.training_mask, bool),
                "weight_seconds": len(np.unique(np.floor(track.times_s))),
            })
        cache[sid] = rows
        source_digests[sid] = {
            "input_manifest_sha256": prepared.input_manifest_sha256,
            "analysis_manifest_sha256": prepared.analysis_manifest_sha256,
            "evidence_sha256": prepared.evidence_sha256,
            "snapshot_digest": prepared.snapshot_digest,
            "source_links_sha256": audit_row["source_links_sha256"],
            "removed_track_ids": audit_row["removed_track_ids"],
            "retained_tracks": len(rows),
            "prediction_receipt": asdict(prediction_receipt),
        }
        print("GATHER", sid, len(rows), "removed", len(audit_row["removed_track_ids"]), flush=True)

    parameters = INITIAL
    rounds = []
    iteration_converged = False
    for index in range(1, MAX_ROUNDS + 1):
        sessions, maps, _ = fixedpoint.select(cache, parameters)
        fitted = fit(sessions)
        updated = (fitted["scale_hz"], fitted["degrees_of_freedom"])
        _, updated_maps, _ = fixedpoint.select(cache, updated)
        status = fixedpoint.convergence(parameters, updated, maps, updated_maps)
        rounds.append({
            "round": index,
            "selection_parameters": {
                "scale_hz": parameters[0], "degrees_of_freedom": parameters[1]},
            "fit": fitted,
            **status,
            "changed_map_tracks": sum(maps[key] != updated_maps[key] for key in maps),
            "track_count": len(maps),
        })
        print("ROUND", index, updated, status, flush=True)
        parameters = updated
        if status["converged"]:
            iteration_converged = True
            break

    sessions, maps, final_tracks = fixedpoint.select(cache, parameters)
    refit = fit(sessions)
    refit_parameters = (refit["scale_hz"], refit["degrees_of_freedom"])
    _, refit_maps, _ = fixedpoint.select(cache, refit_parameters)
    refit_status = fixedpoint.convergence(parameters, refit_parameters, maps, refit_maps)
    converged = iteration_converged and refit_status["converged"]
    output = {
        "protocol": {
            "scope": "six frozen calibration scans; topology-filtered before selection and noise fit; no confirmation scans",
            "initial_parameters": {"scale_hz": INITIAL[0], "degrees_of_freedom": INITIAL[1]},
            "convergence": "scale and df relative changes <1% plus >=99% MAP stability after fresh reselection; final fresh refit must also pass",
            "interpretation": "approximate conditional fixed point after outcome-blind whole-track source-topology exclusion; not a global MLE",
        },
        "converged": converged,
        "iteration_converged": iteration_converged,
        "stopped_reason": ("converged" if converged else
                           "final-refit-check-failed" if iteration_converged else
                           "maximum-rounds-reached"),
        "rounds": rounds,
        "frozen_final_parameters": {
            "scale_hz": parameters[0], "degrees_of_freedom": parameters[1]},
        "final_refit": refit,
        "final_refit_difference": refit_status,
        "source_digests": source_digests,
        "final_tracks": final_tracks,
        "topology_audit_sha256": fixedpoint.digest(audit_bytes),
        "elapsed_s": time.monotonic() - started,
        "code_sha256": fixedpoint.digest(Path(__file__).read_bytes()),
        "robust_core_sha256": fixedpoint.digest((HERE / "robust_core.py").read_bytes()),
        "fit_frequency_sha256": fixedpoint.digest((HERE / "fit_frequency.py").read_bytes()),
        "source_topology_sha256": fixedpoint.digest((CONFIRMATION / "source_topology.py").read_bytes()),
    }
    fixedpoint.atomic(extraction_path, output)
    compatible = {
        "calibration_sessions": sorted(cache),
        "parameters": {
            "scale_hz": parameters[0],
            "degrees_of_freedom": parameters[1],
            "optimizer_success": bool(refit["optimizer_success"]),
        },
        "converged": converged,
        "extraction_file": extraction_path.name,
        "extraction_sha256": fixedpoint.digest(extraction_path.read_bytes()),
        "topology_audit_sha256": output["topology_audit_sha256"],
        "code_sha256": output["code_sha256"],
        "robust_core_sha256": output["robust_core_sha256"],
        "fit_frequency_sha256": output["fit_frequency_sha256"],
        "source_topology_sha256": output["source_topology_sha256"],
    }
    fixedpoint.atomic(parameters_path, compatible)


if __name__ == "__main__":
    main()
