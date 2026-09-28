"""Whole-cohort reporter for paired consistent-calibration grid replays."""
from __future__ import annotations

import json
import math
from pathlib import Path
import statistics

import run_balanced_confirmation as balanced
import run_consistent_replay as replay
from score_confirmation import distance_km


HERE = Path(__file__).resolve().parent
ARMS = ("D", "D_plus_geometry")
VARIANTS = ("old", "consistent")


def exact_selected(actual: dict, expected: dict, label: str) -> None:
    # Source-grid selected rows retain full per-track diagnostics while its
    # point_components intentionally omit `tracks`.  Compare the complete
    # lightweight expected projection, rejecting missing or changed fields.
    if any(key not in actual for key in expected) or {
            key: actual[key] for key in expected} != expected:
        raise ValueError(label + " selected minimum is not reproducible")


def validate_branch(saved: dict, result: dict) -> dict:
    rows = result.get("point_components")
    if not isinstance(rows, list) or not rows:
        raise ValueError("replay branch lacks point components")
    saved_by_point = {
        (float(row["east_km"]), float(row["north_km"])): row
        for row in saved.get("point_components", [])}
    for row in rows:
        if not all(math.isfinite(float(row[key])) for key in (
                "east_km", "north_km", "latitude_deg", "longitude_deg")):
            raise ValueError("nonfinite replay coordinate")
        point = (float(row["east_km"]), float(row["north_km"]))
        source = saved_by_point.get(point)
        if source is None or not all(math.isfinite(float(source[key])) for key in (
                "latitude_deg", "longitude_deg")):
            raise ValueError("saved grid coordinate is missing or nonfinite")
        if (float(row["latitude_deg"]), float(row["longitude_deg"])) != (
                float(source["latitude_deg"]), float(source["longitude_deg"])):
            raise ValueError("replay geographic coordinate differs from saved grid")
        variants = row.get("variant_scores", {})
        if set(variants) != set(VARIANTS):
            raise ValueError("replay variants are missing or unexpected")
        for scores in variants.values():
            if not set(ARMS).issubset(scores) or not all(
                    math.isfinite(float(value)) for value in scores.values()):
                raise ValueError("replay score is missing or nonfinite")
    for row in saved.get("point_components", []):
        if (not all(math.isfinite(float(row[key])) for key in ("east_km", "north_km"))
                or not all(math.isfinite(float(value))
                           for value in row.get("scores", {}).values())):
            raise ValueError("saved grid coordinate or score is nonfinite")
    parity = replay.parity_report(saved, rows, tolerance=1e-7)
    if parity["old_consistent_D_max_absolute_difference"] > 1e-12:
        raise ValueError("replay D invariance failed")
    if result.get("grid_count") != len(rows) or result.get("parity") != parity:
        raise ValueError("saved replay count or parity receipt differs")
    selected = result.get("selected", {})
    if set(selected) != set(VARIANTS):
        raise ValueError("saved replay minima are incomplete")
    for variant in VARIANTS:
        exact_selected(
            selected[variant], replay.select_min(rows, variant, "D_plus_geometry"),
            variant + " joint")
    d_selected = replay.select_min(rows, "old", "D")
    if replay.select_min(rows, "consistent", "D") != d_selected:
        raise ValueError("old and consistent D minima differ")
    saved_rows = saved.get("point_components", [])
    for arm in ARMS:
        expected = min(saved_rows, key=lambda row: (
            float(row["scores"][arm]), float(row["east_km"]),
            float(row["north_km"])))
        exact_selected(saved["arms"][arm]["selected"], expected,
                       "source grid " + arm)
    return {"parity": parity, "D": d_selected,
            "oldJoint": selected["old"], "newJoint": selected["consistent"]}


def boundary_flags(point: dict, saved: dict) -> dict:
    center = saved["seed"]
    radius = float(saved["radius_km"])
    east, north = float(point["east_km"]), float(point["north_km"])
    return {
        "on_grid_edge": (
            math.isclose(abs(east - float(center["east_km"])), 4., abs_tol=1e-10)
            or math.isclose(abs(north - float(center["north_km"])), 4., abs_tol=1e-10)),
        "on_prior_boundary": math.isclose(math.hypot(east, north), radius,
                                           abs_tol=1e-10),
    }


def summarize(rows: list[dict]) -> dict:
    output = {}
    for prior in ("sacramento", "reno"):
        group = [row for row in rows if row["prior"] == prior]
        old_changes = [row["new_minus_old_km"] for row in group]
        d_changes = [row["new_minus_D_km"] for row in group]
        def counts(values):
            return {"improved": sum(value < -1e-9 for value in values),
                    "worsened": sum(value > 1e-9 for value in values),
                    "tied": sum(abs(value) <= 1e-9 for value in values)}
        output[prior] = {
            "cases": len(group),
            "D_mean_km": statistics.mean(row["D_error_km"] for row in group),
            "oldJoint_mean_km": statistics.mean(row["oldJoint_error_km"] for row in group),
            "newJoint_mean_km": statistics.mean(row["newJoint_error_km"] for row in group),
            "old_to_new": counts(old_changes),
            "D_to_new": counts(d_changes),
        }
    return output


def main() -> None:
    target = HERE / "consistent-replay-distances.json"
    if target.exists():
        raise FileExistsError(target)
    entries, _contract = balanced.inputs()
    raw_results = {}
    pending = []
    for entry in entries:
        sid = entry["session_id"]
        path = HERE / f"consistent-replay-{sid}.json"
        if not path.exists():
            pending.append(sid)
            continue
        payload = path.read_bytes()
        result = json.loads(payload)
        if not result.get("finished"):
            pending.append(sid)
            continue
        raw_results[sid] = (payload, result)
    if pending:
        print(json.dumps({"complete": False, "pending_sessions": pending,
                          "status": "Reference distances withheld until all four replays pass."}))
        return

    contract_sha = balanced.base.digest((HERE / "contract.json").read_bytes())
    protocol_sha = balanced.base.digest(
        (HERE / "CONSISTENT_REPLAY_PROTOCOL.md").read_bytes())
    calibration_sha = balanced.base.digest(
        (HERE / "calibration_consistent_calibration.json").read_bytes())
    source_grid_report_bytes = (HERE / "local-grid-distances.json").read_bytes()
    source_grid_report = json.loads(source_grid_report_bytes)
    source_grid_report_sha = balanced.base.digest(source_grid_report_bytes)
    calibration_audit_sha = balanced.base.digest(
        (balanced.PREVIOUS / "audit_source_topology.json").read_bytes())
    second_audit_sha = balanced.base.digest(
        (HERE / "audit_source_topology.json").read_bytes())
    current_code = {
        name: balanced.base.digest((HERE / name).read_bytes()) for name in
        ("run_consistent_replay.py", "paired_reception_evaluator.py",
         "calibration_consistent_fit.py")}
    completed = {}
    result_hashes = {}
    validated = {}

    # Gate the entire cohort before parsing the manifest/reference coordinates.
    for entry in entries:
        sid = entry["session_id"]
        payload, result = raw_results[sid]
        grid_path = HERE / f"local-grid-{sid}.json"
        grid_bytes = grid_path.read_bytes()
        grid = json.loads(grid_bytes)
        grid_protocol_sha = balanced.base.digest(
            (HERE / "LOCAL_GRID_PROTOCOL.md").read_bytes())
        local_runner_sha = balanced.base.digest((HERE / "run_local_grid.py").read_bytes())
        if (result.get("session_id") != sid or
                result.get("contract_sha256") != contract_sha or
                result.get("source_grid_sha256") != balanced.base.digest(grid_bytes) or
                result.get("source_grid_report_sha256") != source_grid_report_sha or
                not source_grid_report.get("complete") or
                source_grid_report.get("artifact_sha256", {}).get(sid) != balanced.base.digest(grid_bytes) or
                result.get("consistent_calibration_sha256") != calibration_sha or
                result.get("consistent_replay_protocol_sha256") != protocol_sha or
                result.get("cache_sha256") != entry["cache_sha256"] or
                result.get("input_manifest_sha256") != entry["input_manifest_sha256"] or
                result.get("analysis_manifest_sha256") != entry["analysis_manifest_sha256"] or
                result.get("evidence_sha256") != grid.get("evidence_sha256") or
                result.get("snapshot_digest") != grid.get("snapshot_digest") or
                result.get("calibration_topology_audit_sha256") != calibration_audit_sha or
                result.get("topology_audit_sha256") != second_audit_sha or
                result.get("topology_audit_sha256") != grid.get("topology_audit_sha256") or
                result.get("model_hashes") != grid.get("model_hashes") or
                result.get("parameters") != grid.get("parameters") or
                result.get("code_sha256") != current_code or
                not grid.get("finished") or grid.get("session_id") != sid or
                grid.get("deduplicate_reception") is not False or
                grid.get("contract_sha256") != contract_sha or
                grid.get("local_grid_protocol_sha256") != grid_protocol_sha or
                grid.get("code_sha256", {}).get("run_local_grid.py") != local_runner_sha):
            raise ValueError("replay artifact binding or current source changed")
        if set(result.get("branches", {})) != set(balanced.base.PRIORS):
            raise ValueError("replay artifact lacks an independent prior")
        validated[sid] = {
            prior: validate_branch(grid["branches"][prior], result["branches"][prior])
            for prior in balanced.base.PRIORS}
        completed[sid] = (result, grid)
        result_hashes[sid] = balanced.base.digest(payload)

    manifest = json.loads((HERE / "manifest.json").read_text())
    if [item["pose"]["session_id"] for item in manifest["sessions"]] != [
            entry["session_id"] for entry in entries]:
        raise ValueError("reference manifest cohort/order differs")
    rows = []
    for item in manifest["sessions"]:
        sid = item["pose"]["session_id"]
        truth = item["pose"]["pose_authority"]
        reference = (truth["latitude_deg"], truth["longitude_deg"])
        _result, grid = completed[sid]
        for prior in balanced.base.PRIORS:
            points = validated[sid][prior]
            def error(point):
                return distance_km(
                    (point["latitude_deg"], point["longitude_deg"]), reference)
            d_error = error(points["D"])
            old_error = error(points["oldJoint"])
            new_error = error(points["newJoint"])
            rows.append({
                "session_id": sid, "prior": prior,
                "D_error_km": d_error,
                "oldJoint_error_km": old_error,
                "newJoint_error_km": new_error,
                "new_minus_old_km": new_error - old_error,
                "new_minus_D_km": new_error - d_error,
                "coordinates": {name: [point["latitude_deg"], point["longitude_deg"]]
                                for name, point in (("D", points["D"]),
                                    ("oldJoint", points["oldJoint"]),
                                    ("newJoint", points["newJoint"]))},
                "boundary_flags": {name: boundary_flags(point, grid["branches"][prior])
                                   for name, point in (("D", points["D"]),
                                       ("oldJoint", points["oldJoint"]),
                                       ("newJoint", points["newJoint"]))},
                "parity": points["parity"],
            })
    output = {
        "complete": True,
        "scope": "Posthoc development paired fixed-grid calibration-consistency diagnostic; operator reference is not surveyed truth.",
        "rows": rows,
        "prior_aggregate": summarize(rows),
        "replay_sha256": result_hashes,
        "contract_sha256": contract_sha,
        "consistent_calibration_sha256": calibration_sha,
        "consistent_replay_protocol_sha256": protocol_sha,
        "reporter_sha256": balanced.base.digest(Path(__file__).read_bytes()),
    }
    balanced.base.atomic(target, output)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
