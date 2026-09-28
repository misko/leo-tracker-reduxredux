"""Coordinator audit of cumulative estimates, including original wave2 provenance."""

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import ds7_eval as e  # noqa: E402


def verify_inventory(path):
    seal = e.read_json(path)
    assert e.seal_object({k: v for k, v in seal.items() if k != "content_sha256"}) == seal
    assert {str(p.relative_to(path.parent)) for p in path.parent.rglob("*") if p.is_file()} == set(
        seal["files"]
    ) | {"seal.json"}
    for name, digest in seal["files"].items():
        assert e.file_digest(path.parent / name) == digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs = e.read_sealed(args.inputs, "ds7-inputs/v1")
    old_root = ROOT / "reports/2026_09_27_ds7_wave2"
    provenance = old_root / "review/scan-estimate-provenance-first8.json"
    old = {r["session_id"]: r for r in e.read_json(provenance)["rows"]}
    lookup = {}
    for path in (ROOT / "reports").glob("2026_09_27_ds7_wave*/coordinator/*/scores.json"):
        data = e.read_json(path)
        for row in data["trials"]:
            lookup[(data["run_seal_sha256"], row["unit_id"])] = (path, row)
    rows = []
    verified = set()
    for row in inputs["captures"]:
        if row["state"] != "ready":
            continue
        assert len(row["artifacts"]) == 1
        artifact = row["artifacts"][0]
        assert artifact["kind"] == "scan_estimate"
        estimate_path = Path(artifact["path"])
        assert e.file_digest(estimate_path) == artifact["sha256"]
        data = e.read_json(estimate_path)
        assert data["session_id"] == row["session_id"]
        assert data["manifest_sha256"] == row["manifest_sha256"]
        if "source" in data:
            source = data["source"]
            for kind in ("request", "response", "seal"):
                assert e.file_digest(Path(source[kind + "_path"])) == source[kind + "_sha256"]
            response_path = Path(source["response_path"])
            seal_path = Path(source["seal_path"])
        else:
            binding = old[row["session_id"]]
            assert binding["scan_estimate_sha256"] == artifact["sha256"]
            response_path = old_root / binding["source_response"]
            seal_path = response_path.parent.parent / "seal.json"
            assert e.file_digest(response_path) == binding["source_response_sha256"]
            assert e.file_digest(seal_path) == binding["source_seal_sha256"]
        if seal_path not in verified:
            verify_inventory(seal_path)
            verified.add(seal_path)
        response = e.read_json(response_path)
        request = e.read_json(response_path.parent / "request.json")
        assert request["unit"]["session_ids"] == [row["session_id"]]
        assert request["captures"][0]["manifest_sha256"] == row["manifest_sha256"]
        assert request["unit"]["unit_id"] == response["unit_id"]
        for key in ("status", "converged", "boundary_hit", "estimate", "rf_rms_hz"):
            assert data[key] == response[key]
        qualified = (
            data["status"] == "ok" and data["converged"] is True and data["boundary_hit"] is False
        )
        seal_digest = e.file_digest(seal_path)
        score_path, score = lookup[(seal_digest, response["unit_id"])]
        verify_inventory(score_path.parent / "seal.json")
        assert score["qualified"] == qualified
        rows.append(
            {
                "session_id": row["session_id"],
                "unit_id": response["unit_id"],
                "error_m": score["horizontal_error_m"],
                "qualified": qualified,
                "status": data["status"],
                "boundary_hit": data["boundary_hit"],
                "score_path": str(score_path),
                "score_sha256": e.file_digest(score_path),
                "source_seal_path": str(seal_path),
                "source_seal_sha256": seal_digest,
            }
        )
    errors = [r["error_m"] for r in rows]
    summary = {
        "evaluated": len(rows),
        "qualified": sum(r["qualified"] for r in rows),
        "boundary_count": sum(r["boundary_hit"] for r in rows),
        "total": len(inputs["captures"]),
        "below_1km": sum(r["qualified"] and r["error_m"] < 1000 for r in rows),
        "better_than_prior_809m": sum(
            r["qualified"] and r["error_m"] < 809.029031551158 for r in rows
        ),
        "median_m": statistics.median(errors),
        "min_m": min(errors),
        "max_m": max(errors),
    }
    e.write_json(
        args.output,
        e.seal_object(
            {
                "schema": "ds7-coordinator-estimate-audit/v1",
                "inputs_sha256": e.file_digest(args.inputs),
                "old_provenance_sha256": e.file_digest(provenance),
                "audit_script_sha256": e.file_digest(Path(__file__)),
                "summary": summary,
                "trials": sorted(rows, key=lambda r: r["unit_id"]),
                "limitation": (
                    "Individual results on exposed single-site unsurveyed reference; "
                    "not a pooled full88 result."
                ),
            }
        ),
    )
    print(summary)


if __name__ == "__main__":
    main()
