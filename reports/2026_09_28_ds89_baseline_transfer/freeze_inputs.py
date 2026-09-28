"""Validate and bind preflight inputs for the unchanged numerical baseline."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


plan = json.loads((HERE / "plan.json").read_text())
template = json.loads(
    (ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/request.json").read_text()
)
sources = {r["dataset_id"]: r for r in plan["sources"]}
for unit in ("DS8-001", "DS9-001"):
    row = next(r for r in plan["captures"] if r["unit_id"] == unit)
    folder = HERE / "exports" / unit
    paths = [
        folder / "observations.json",
        folder / "banks/manifest.json",
        folder / "banks/banks.npz",
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
        "schema": "ds7-request/v1",
        "dataset_sha256": "sha256:" + sources[row["dataset_id"]]["sha256"],
        "model_id": template["model_id"],
        "config": template["config"],
        "unit": {"kind": "single", "unit_id": unit, "session_ids": [row["session_id"]]},
        "captures": [row],
        "inputs": [input_row],
        "plan_sha256": digest(HERE / "plan.json"),
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
        evidence_path = (
            ROOT / "reports/2026_09_28_ds9_post_ds8/analysis" / (row["session_id"] + ".json")
        )
        assert digest(evidence_path) == row["mint_analysis_evidence_sha256"]
        evidence = json.loads(evidence_path.read_text())
        mint_match = (
            evidence["glrt"]["metrics_manifest_sha256"] == document["analysis_manifest_sha256"]
        )
    validation = {
        "unit_id": unit,
        "session_id": row["session_id"],
        "tracks": len(document["tracks"]),
        "training_observations": sum(int(t["mask"].sum()) for t in document["tracks"]),
        "held_observations": sum(int((~t["mask"]).sum()) for t in document["tracks"]),
        "exclusions": document["eligibility_exclusions"],
        "catalogue_size": manifest["catalogue_size"],
        "mint_glrt_metrics_match": mint_match,
        "analysis_manifest_sha256": document["analysis_manifest_sha256"],
        "artifacts": artifacts,
    }
    out = HERE / "solver" / unit
    out.mkdir(parents=True, exist_ok=False)
    with (out / "request.json").open("x") as stream:
        json.dump(request, stream, indent=2)
    with (out / "input-validation.json").open("x") as stream:
        json.dump(validation, stream, indent=2)
    print(json.dumps({k: v for k, v in validation.items() if k != "artifacts"}), flush=True)
