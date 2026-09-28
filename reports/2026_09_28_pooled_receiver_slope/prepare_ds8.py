"""One separately bounded export from the original DS8-008 observation bytes."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_export_baseline as exporter  # noqa: E402
import ds7_fast_baseline_adapter as baseline  # noqa: E402

pre = ROOT / "reports/2026_09_28_ds89_baseline_transfer"
old = ROOT / "reports/2026_09_28_ds89_baseline_panel"
plan = json.loads((pre / "plan.json").read_text())
row = next(r for r in plan["captures"] if r["unit_id"] == "DS8-008")
source = next(r for r in plan["sources"] if r["dataset_id"] == "DS8")
assert hashlib.sha256((ROOT / source["path"]).read_bytes()).hexdigest() == source["sha256"]
observation = old / "exports/DS8-008/observations.json"
old_seal = json.loads((old / "solver/DS8-008/fit-seal.json").read_text())["sha256"]
assert (
    hashlib.sha256(observation.read_bytes()).hexdigest()
    == old_seal[str(observation.relative_to(ROOT))]
)
out = HERE / "preparation/DS8-008"
exporter.export_banks(
    row, observation, out / "banks", Path("/srv/bulk/leo"), Path("/var/lib/leo/tle")
)
template = json.loads((pre / "solver/DS8-001/request.json").read_text())
paths = [observation, out / "banks/manifest.json", out / "banks/banks.npz"]
artifacts = [
    {
        "kind": "observations" if i == 0 else "candidates",
        "path": str(p),
        "sha256": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    for i, p in enumerate(paths)
]
inputs = [
    {
        "session_id": row["session_id"],
        "manifest_sha256": row["manifest_sha256"],
        "artifacts": artifacts,
    }
]
request = {
    **template,
    "unit": {"kind": "single", "unit_id": "DS8-008", "session_ids": [row["session_id"]]},
    "captures": [row],
    "inputs": inputs,
    "inputs_sha256": "sha256:"
    + hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
}
document = baseline.load_documents(request)[0]
assert document["sample_rate_hz"] == row["sample_rate_hz"]
manifest = json.loads(paths[1].read_text())
assert all(
    p["collected_utc_ns"] < document["start_utc_ns"] - 505_000_000_000
    for p in manifest["provider_sources"]
)
with (out / "request.json").open("x") as f:
    json.dump(request, f, indent=2)
with (out / "validation.json").open("x") as f:
    json.dump(
        {
            "unit_id": "DS8-008",
            "tracks": len(document["tracks"]),
            "exclusions": document["eligibility_exclusions"],
            "sample_rate_hz": document["sample_rate_hz"],
            "analysis_manifest_sha256": document["analysis_manifest_sha256"],
            "causal_provider_check": True,
        },
        f,
        indent=2,
    )
print(
    json.dumps({"unit_id": "DS8-008", "tracks": len(document["tracks"]), "state": "validated"}),
    flush=True,
)
