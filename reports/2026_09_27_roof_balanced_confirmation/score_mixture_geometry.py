"""Whole-cohort distance reporting after fixed-grid mixture replay validation."""
import json
from pathlib import Path

import mixture_geometry_models as models
import mixture_geometry_reporting as reporting
import run_mixture_geometry_replay as runner

HERE = Path(__file__).resolve().parent


def main():
    target = HERE / "mixture-geometry-distances.json"
    if target.exists():
        raise FileExistsError(target)
    entries, _ = runner.balanced.inputs()
    runs = {}
    pending = []
    for entry in entries:
        sid = entry["session_id"]
        path = HERE / f"mixture-geometry-replay-{sid}.json"
        if not path.exists():
            pending.append(sid)
            continue
        payload = path.read_bytes()
        result = json.loads(payload)
        if not result.get("finished"):
            pending.append(sid)
        else:
            runs[sid] = (result, runner.base.digest(payload))
    if pending:
        print(json.dumps({"complete": False, "pending_sessions": pending}))
        return

    bundle = models.load_geometry_bundle()
    grid_report_bytes = (HERE / "local-grid-distances.json").read_bytes()
    grid_report = json.loads(grid_report_bytes)
    if not grid_report.get("complete") or grid_report.get("deduplicate_reception") is not False:
        raise ValueError("source grid report is not a completed primary comparison")
    common = {
        "contract_sha256": runner.base.digest((HERE / "contract.json").read_bytes()),
        "calibration_sha256": bundle.calibration_sha256,
        "geometry_protocol_sha256": runner.base.digest((HERE / "MIXTURE_GEOMETRY_PROTOCOL.md").read_bytes()),
        "source_grid_report_sha256": runner.base.digest(grid_report_bytes),
        "calibration_topology_audit_sha256": runner.base.digest(
            (runner.PREVIOUS / "audit_source_topology.json").read_bytes()),
        "topology_audit_sha256": runner.base.digest((HERE / "audit_source_topology.json").read_bytes()),
    }
    code = {name: runner.base.digest((HERE / name).read_bytes()) for name in (
        "run_mixture_geometry_replay.py", "mixture_geometry_models.py",
        "paired_reception_evaluator.py", "run_consistent_replay.py")}
    validated, grids = {}, {}
    for entry in entries:
        sid = entry["session_id"]
        result, _ = runs[sid]
        grid_bytes = (HERE / f"local-grid-{sid}.json").read_bytes()
        grid = json.loads(grid_bytes)
        grid_sha = runner.base.digest(grid_bytes)
        if (result.get("session_id") != sid or result.get("code_sha256") != code or
                any(result.get(key) != value for key, value in common.items()) or
                result.get("source_grid_sha256") != grid_sha or
                grid_report.get("artifact_sha256", {}).get(sid) != grid_sha or
                result.get("calibration_source_hashes") != dict(bundle.source_hashes) or
                result.get("calibration_artifact_sha256") != dict(bundle.artifact_sha256) or
                result.get("calibration_sessions") != list(bundle.calibration_sessions) or
                any(result.get(key) != entry[key] for key in (
                    "cache_sha256", "input_manifest_sha256", "analysis_manifest_sha256")) or
                any(result.get(key) != grid.get(key) for key in (
                    "evidence_sha256", "snapshot_digest", "model_hashes", "parameters",
                    "topology_receipt", "contract_sha256", "topology_audit_sha256"))):
            raise ValueError("mixture replay input/model/code/grid binding changed")
        if (not grid.get("finished") or grid.get("session_id") != sid or
                grid.get("deduplicate_reception") is not False or
                set(result.get("branches", {})) != set(runner.base.PRIORS) or
                set(grid.get("branches", {})) != set(runner.base.PRIORS)):
            raise ValueError("incomplete primary source grid or independent priors")
        branches = {}
        for prior in runner.base.PRIORS:
            source, branch = grid["branches"][prior], result["branches"][prior]
            if branch.get("origin") != source.get("origin"):
                raise ValueError("prior origin changed")
            branches[prior] = reporting.validate_branch(source, branch)
            if branch.get("parity") != runner.parity_report(source, branch["point_components"]):
                raise ValueError("producer parity receipt changed")
        validated[sid], grids[sid] = branches, grid

    # No reference distances are computed until every recording passes.
    manifest = json.loads((HERE / "manifest.json").read_bytes())
    if [row["pose"]["session_id"] for row in manifest["sessions"]] != [
            entry["session_id"] for entry in entries]:
        raise ValueError("reference cohort/order changed")
    rows = []
    for item in manifest["sessions"]:
        sid = item["pose"]["session_id"]
        pose = item["pose"]["pose_authority"]
        reference = (pose["latitude_deg"], pose["longitude_deg"])
        for prior in runner.base.PRIORS:
            rows.append(reporting.distance_row(
                sid, prior, grids[sid]["branches"][prior], validated[sid][prior], reference))
    output = {
        "complete": True, "rows": rows,
        "summary": reporting.summarize(
            rows, [entry["session_id"] for entry in entries]),
        "replay_sha256": {sid: digest for sid, (_, digest) in runs.items()},
        "bindings": common,
        "reporter_sha256": {name: runner.base.digest((HERE / name).read_bytes()) for name in (
            "score_mixture_geometry.py", "mixture_geometry_reporting.py",
            "score_consistent_replay.py")},
        "scope": "Posthoc fixed-coordinate development comparison; reference is operator supplied, not surveyed. No prospective resolution claim.",
    }
    runner.base.atomic(target, output)
    print(json.dumps(output["summary"], indent=2))


if __name__ == "__main__":
    main()
