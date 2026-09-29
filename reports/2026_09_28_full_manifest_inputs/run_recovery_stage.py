"""Recover DS9-F028 in separate paths while preserving its original failure."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_export_baseline as exporter  # noqa: E402
import ds7_fast_baseline_adapter as baseline  # noqa: E402

unit, stage = sys.argv[1:]
assert unit == "DS9-F028"
plan = json.loads((HERE / "plan.json").read_text())
row = next(r for r in plan["captures"] if r["unit_id"] == unit)
assert (
    "sha256:" + hashlib.sha256((ROOT / row["dataset_manifest_path"]).read_bytes()).hexdigest()
    == row["dataset_sha256"]
)
folder = HERE / "recovery-exports" / unit
if stage == "observations":
    result = exporter.export(
        row, folder / "observations.json", Path("/srv/bulk/leo"), Path("/var/lib/leo/tle")
    )
    previous = json.loads((HERE / "exports" / unit / "observations.json").read_text())
    assert {k: v for k, v in result.items() if k != "elapsed_seconds"} == {
        k: v for k, v in previous.items() if k != "elapsed_seconds"
    }, "Recovery changed scientific observation content"
    print("tracks", len(result["tracks"]))
elif stage == "banks":
    result = exporter.export_banks(
        row,
        folder / "observations.json",
        folder / "banks",
        Path("/srv/bulk/leo"),
        Path("/var/lib/leo/tle"),
    )
    print("tracks", len(result["tracks"]))
elif stage == "validate":
    inputs = row["reused_input"]
    if inputs is None:
        paths = [
            folder / "observations.json",
            folder / "banks/manifest.json",
            folder / "banks/banks.npz",
        ]
        inputs = {
            "session_id": row["session_id"],
            "manifest_sha256": row["manifest_sha256"],
            "artifacts": [
                {
                    "kind": "observations" if i == 0 else "candidates",
                    "path": str(p),
                    "sha256": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest(),
                }
                for i, p in enumerate(paths)
            ],
        }
    for artifact in inputs["artifacts"]:
        assert (
            "sha256:" + hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest()
            == artifact["sha256"]
        )
    request = {"config": plan["config"], "inputs": [inputs]}
    document = baseline.load_documents(request)[0]
    assert document["sample_rate_hz"] == row["sample_rate_hz"]
    manifest_path = next(
        Path(a["path"])
        for a in inputs["artifacts"]
        if a["kind"] == "candidates" and a["path"].endswith(".json")
    )
    bank = json.loads(manifest_path.read_text())
    assert all(
        p["collected_utc_ns"] < document["start_utc_ns"] - 505_000_000_000
        for p in bank["provider_sources"]
    )
    mint_match = None
    if row["dataset_id"] == "DS9":
        mint = ROOT / "reports/2026_09_28_ds9_post_ds8/analysis" / (row["session_id"] + ".json")
        assert (
            "sha256:" + hashlib.sha256(mint.read_bytes()).hexdigest()
            == row["mint_analysis_evidence_sha256"]
        )
        mint_match = (
            json.loads(mint.read_text())["glrt"]["metrics_manifest_sha256"]
            == document["analysis_manifest_sha256"]
        )
        assert mint_match, "DS9 minted GLRT evidence differs from exported observations"
    result = {
        "unit_id": unit,
        "session_id": row["session_id"],
        "dataset_id": row["dataset_id"],
        "request": request,
        "tracks": len(document["tracks"]),
        "eligibility_exclusions": document["eligibility_exclusions"],
        "training_observations": sum(int(t["mask"].sum()) for t in document["tracks"]),
        "held_observations": sum(int((~t["mask"]).sum()) for t in document["tracks"]),
        "analysis_manifest_sha256": document["analysis_manifest_sha256"],
        "mint_glrt_metrics_match": mint_match,
        "sample_rate_hz": document["sample_rate_hz"],
        "provider_sources": bank["provider_sources"],
    }
    with (HERE / "recovery-validated" / (unit + ".json")).open("x") as stream:
        json.dump(result, stream, indent=2)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("request", "eligibility_exclusions")}
        )
    )
else:
    raise ValueError(stage)
