"""Freeze compact completed records; never modify live inference artifacts."""

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from report_dsx01_radial_restarts import compact_record, raw_denominators, run

LIVE = ROOT / "reports/2026_10_18_dsx01_radial_restarts"
OUT = Path(__file__).resolve().parent


def main():
    if (OUT / "snapshot_receipt.json").exists():
        raise RuntimeError("snapshot already frozen")
    protocol = json.loads((LIVE / "protocol.json").read_text())
    (OUT / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    bindings = {}
    totals, _ = raw_denominators()
    paths = sorted(LIVE.glob("DSX*/*/start_*/result.json"))
    for path in paths:
        payload = path.read_bytes()
        data = json.loads(payload)
        compact = compact_record(data)
        compact["total_glrt_points"] = totals[data["case"]]
        compact["provenance"] = data.get("provenance", {})
        for key in (
            "source_fingerprint", "discovery_sha256", "status", "seconds", "sigma_hz",
            "curved_points", "tracked_glrt_points", "candidate_count", "actual_report_inputs_read",
            "input_audit", "GPS_or_following_TLE_used", "regional_center", "box_width_km",
        ):
            if key in data:
                compact[key] = data[key]
        for row, original in zip(compact.get("rounds", []), data.get("rounds", [])):
            for key in ("round", "reassociation", "assignment_rows", "aliases"):
                if key in original:
                    row[key] = original[key]
            if "assignment_rows" in row:
                row["assignment_rows"] = [
                    {key: value for key, value in item.items() if key not in {
                        "residual_hz", "innovations_hz", "times_s", "feasible_candidates", "parts"
                    }} for item in row["assignment_rows"]
                ]
        rel = path.relative_to(LIVE)
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(compact, indent=2) + "\n")
        bindings[str(rel)] = {
            "original_result_sha256": hashlib.sha256(payload).hexdigest(),
            "compact_result_sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
        }
    for name in ("consistency_audit.json", "endpoint_gradient_replay.json", "run_receipt.json", "worker_status.json"):
        if (LIVE / name).exists():
            shutil.copy2(LIVE / name, OUT / name)
    source_paths = set(protocol["source_bindings"])
    source_paths.update(str(p.relative_to(ROOT)) for p in (ROOT / "tools").glob("*radial*py"))
    source_paths.update(str(p.relative_to(ROOT)) for p in (ROOT / "tests/analysis").glob("test_dsx01_radial*py"))
    for rel in sorted(source_paths):
        source = ROOT / rel
        if source.is_file() and source.suffix == ".py":
            dest = OUT / "source_snapshot" / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    (OUT / "live_result_bindings.json").write_text(json.dumps(bindings, indent=2) + "\n")
    audit = run(OUT)
    receipt = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_live_directory": str(LIVE),
        "completed_paired_runs": len(paths),
        "expected_paired_runs": protocol["expected_pipeline_results"],
        "campaign_complete": len(paths) == protocol["expected_pipeline_results"],
        "finite_endpoints": audit["finite_arm_endpoints"],
        "full_results_retained_locally": True,
        "published_records_are_compact": True,
        "compact_records_support_plot_reproduction_not_full_objective_replay": True,
    }
    (OUT / "snapshot_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
