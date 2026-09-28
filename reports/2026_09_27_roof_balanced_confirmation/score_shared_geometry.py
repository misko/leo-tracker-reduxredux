"""Report the complete four-scan shared-effect replay after independent checks."""
import json
from pathlib import Path

import run_shared_geometry_replay as runner
import shared_geometry_reporting as reporting

HERE = Path(__file__).resolve().parent


def main():
    target = HERE / "shared-geometry-distances.json"
    if target.exists():
        raise FileExistsError(target)
    entries, _ = runner.balanced.inputs()
    runs = {}
    pending = []
    for entry in entries:
        sid = entry["session_id"]
        path = HERE / f"shared-geometry-replay-{sid}.json"
        if not path.exists():
            pending.append(sid)
            continue
        payload = path.read_bytes(); result = json.loads(payload)
        if not result.get("finished"):
            pending.append(sid)
        else:
            runs[sid] = (result, runner.base.digest(payload))
    if pending:
        print(json.dumps({"complete": False, "pending_sessions": pending}))
        return

    bundle = runner.mixture_geometry_models.load_geometry_bundle()
    random_binding, _ = runner.random_effect_binding()
    report_bytes = (HERE / "mixture-geometry-distances.json").read_bytes()
    previous_report = json.loads(report_bytes)
    if not previous_report.get("complete"):
        raise ValueError("previous geographic report is incomplete")
    common = {
        "contract_sha256": runner.base.digest((HERE / "contract.json").read_bytes()),
        "shared_geometry_protocol_sha256": runner.base.digest((HERE / "SHARED_GEOMETRY_PROTOCOL.md").read_bytes()),
        "random_effect_binding": random_binding,
        "calibration_sha256": bundle.calibration_sha256,
        "calibration_sessions": list(bundle.calibration_sessions),
        "calibration_source_hashes": dict(bundle.source_hashes),
        "calibration_artifact_sha256": dict(bundle.artifact_sha256),
        "source_replay_report_sha256": runner.base.digest(report_bytes),
        "source_grid_report_sha256": runner.base.digest((HERE / "local-grid-distances.json").read_bytes()),
        "topology_audit_sha256": runner.base.digest((HERE / "audit_source_topology.json").read_bytes()),
    }
    code = {name: runner.base.digest((HERE / name).read_bytes()) for name in (
        "run_shared_geometry_replay.py", "shared_effect_evaluator.py",
        "detection_random_intercept_refined.py", "mixture_geometry_models.py",
        "paired_reception_evaluator.py", "run_consistent_replay.py")}
    validated = {}; grids = {}; parity_receipts = {}
    for entry in entries:
        sid = entry["session_id"]; result, _ = runs[sid]
        source_bytes = (HERE / f"mixture-geometry-replay-{sid}.json").read_bytes()
        source = json.loads(source_bytes)
        grid_bytes = (HERE / f"local-grid-{sid}.json").read_bytes()
        grid = json.loads(grid_bytes)
        if (result.get("session_id") != sid or result.get("code_sha256") != code or
                any(result.get(k) != v for k, v in common.items()) or
                result.get("source_replay_sha256") != runner.base.digest(source_bytes) or
                previous_report.get("replay_sha256", {}).get(sid) != runner.base.digest(source_bytes) or
                result.get("source_grid_sha256") != runner.base.digest(grid_bytes) or
                source.get("source_grid_sha256") != runner.base.digest(grid_bytes) or
                any(result.get(k) != entry[k] for k in (
                    "cache_sha256", "input_manifest_sha256", "analysis_manifest_sha256")) or
                any(result.get(k) != source.get(k) for k in (
                    "evidence_sha256", "snapshot_digest", "topology_receipt", "parameters", "model_hashes"))):
            raise ValueError("shared replay input/model/code/source binding changed")
        if (not source.get("finished") or not grid.get("finished") or
                source.get("session_id") != sid or grid.get("session_id") != sid or
                grid.get("deduplicate_reception") is not False or
                any(set(x.get("branches", {})) != set(runner.base.PRIORS) for x in (result, source, grid))):
            raise ValueError("incomplete prior/grid inventory")
        validated[sid] = {}; parity_receipts[sid] = {}; grids[sid] = grid
        for prior in runner.base.PRIORS:
            branch = result["branches"][prior]
            if branch.get("origin") != source["branches"][prior].get("origin"):
                raise ValueError("independent prior origin changed")
            validated[sid][prior] = reporting.validate_branch(grid["branches"][prior], branch)
            parity = runner.parity_report(source["branches"][prior], branch["point_components"])
            if branch.get("parity") != parity:
                raise ValueError("producer parity receipt differs")
            parity_receipts[sid][prior] = parity

    # The reference is opened only after all eight branches pass the above checks.
    manifest_bytes = (HERE / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if [row["pose"]["session_id"] for row in manifest["sessions"]] != [e["session_id"] for e in entries]:
        raise ValueError("reference cohort/order changed")
    rows = []
    for item in manifest["sessions"]:
        sid = item["pose"]["session_id"]; pose = item["pose"]["pose_authority"]
        for prior in runner.base.PRIORS:
            rows.append(reporting.distance_row(sid, prior, grids[sid]["branches"][prior],
                validated[sid][prior], (pose["latitude_deg"], pose["longitude_deg"])))
    result = {"complete": True, "rows": rows,
        "summary": reporting.summarize(rows, [e["session_id"] for e in entries]),
        "replay_sha256": {sid: h for sid, (_, h) in runs.items()},
        "bindings": common, "parity": parity_receipts,
        "manifest_sha256": runner.base.digest(manifest_bytes),
        "reporter_sha256": {name: runner.base.digest((HERE / name).read_bytes()) for name in (
            "score_shared_geometry.py", "shared_geometry_reporting.py", "score_consistent_replay.py")},
        "scope": "Already-unblinded development cohort; operator-supplied roof reference, not surveyed truth. No resolution claim."}
    runner.base.atomic(target, result)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
