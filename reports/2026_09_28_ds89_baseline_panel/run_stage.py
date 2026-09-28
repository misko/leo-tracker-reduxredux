"""One bounded stage, reusing the unchanged public exporter and baseline model."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE.parent / "2026_09_28_ds89_baseline_transfer"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_export_baseline as exporter  # noqa: E402
import ds7_fast_baseline_adapter as baseline  # noqa: E402


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("unit")
parser.add_argument("stage", choices=("observations", "banks", "freeze", "fit"))
args = parser.parse_args()
plan = json.loads((PREFLIGHT / "plan.json").read_text())
row = next(r for r in plan["captures"] if r["unit_id"] == args.unit)
assert not args.unit.endswith("-001")
source = next(s for s in plan["sources"] if s["dataset_id"] == row["dataset_id"])
assert digest(ROOT / source["path"]) == "sha256:" + source["sha256"]
export = HERE / "exports" / args.unit
solver = HERE / "solver" / args.unit
if args.stage == "observations":
    result = exporter.export(
        row, export / "observations.json", Path("/srv/bulk/leo"), Path("/var/lib/leo/tle")
    )
    print(
        json.dumps({"tracks": len(result["tracks"]), "elapsed_seconds": result["elapsed_seconds"]})
    )
elif args.stage == "banks":
    result = exporter.export_banks(
        row,
        export / "observations.json",
        export / "banks",
        Path("/srv/bulk/leo"),
        Path("/var/lib/leo/tle"),
    )
    print(
        json.dumps({"tracks": len(result["tracks"]), "elapsed_seconds": result["elapsed_seconds"]})
    )
elif args.stage == "freeze":
    template = json.loads(
        (PREFLIGHT / "solver" / f"{row['dataset_id']}-001" / "request.json").read_text()
    )
    paths = [
        export / "observations.json",
        export / "banks/manifest.json",
        export / "banks/banks.npz",
    ]
    artifacts = [
        {"kind": "observations" if i == 0 else "candidates", "path": str(p), "sha256": digest(p)}
        for i, p in enumerate(paths)
    ]
    input_row = {
        "session_id": row["session_id"],
        "manifest_sha256": row["manifest_sha256"],
        "artifacts": artifacts,
    }
    request = {
        **template,
        "unit": {"kind": "single", "unit_id": args.unit, "session_ids": [row["session_id"]]},
        "captures": [row],
        "inputs": [input_row],
        "inputs_sha256": "sha256:"
        + hashlib.sha256(json.dumps([input_row], sort_keys=True).encode()).hexdigest(),
    }
    document = baseline.load_documents(request)[0]
    assert document["sample_rate_hz"] == row["sample_rate_hz"]
    manifest = json.loads(paths[1].read_text())
    assert all(
        p["collected_utc_ns"] < document["start_utc_ns"] - 505_000_000_000
        for p in manifest["provider_sources"]
    )
    mint_match = None
    if row["dataset_id"] == "DS9":
        path = ROOT / "reports/2026_09_28_ds9_post_ds8/analysis" / (row["session_id"] + ".json")
        assert digest(path) == row["mint_analysis_evidence_sha256"]
        mint_match = (
            json.loads(path.read_text())["glrt"]["metrics_manifest_sha256"]
            == document["analysis_manifest_sha256"]
        )
    validation = {
        "unit_id": args.unit,
        "tracks": len(document["tracks"]),
        "exclusions": document["eligibility_exclusions"],
        "mint_glrt_metrics_match": mint_match,
        "training_observations": sum(int(t["mask"].sum()) for t in document["tracks"]),
        "held_observations": sum(int((~t["mask"]).sum()) for t in document["tracks"]),
        "analysis_manifest_sha256": document["analysis_manifest_sha256"],
    }
    write(solver / "request.json", request)
    write(solver / "input-validation.json", validation)
    print(json.dumps(validation))
else:
    request = json.loads((solver / "request.json").read_text())
    for artifact in request["inputs"][0]["artifacts"]:
        assert digest(Path(artifact["path"])) == artifact["sha256"]
    response = baseline.estimate(request)
    write(solver / "response.json", response)
    print(
        json.dumps(
            {
                k: response[k]
                for k in ("unit_id", "status", "converged", "boundary_hit")
                if k in response
            }
        )
    )
