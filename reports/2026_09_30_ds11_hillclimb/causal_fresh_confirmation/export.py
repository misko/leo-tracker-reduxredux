"""Bounded sequential original-bank exports for causal-fresh confirmation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PLAN = HERE / "export-plan.json"
FULL_MANIFEST = HERE.parent.parent / "2026_09_30_ds11_post_ds10/local/manifest.json"
ANALYSIS = HERE.parent.parent / "2026_09_30_ds11_post_ds10/local/analysis"
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_export_plan(plan):
    if plan.get("schema") != "ds11-causal-fresh-confirmation-export-plan/v1":
        raise ValueError("export plan schema mismatch")
    if [row["full_manifest_index"] for row in plan["captures"]] != [10, 18, 35, 60, 75]:
        raise ValueError("confirmation membership mismatch")
    for name, expected in plan["source_sha256"].items():
        if digest(name) != expected:
            raise ValueError(f"source digest mismatch: {name}")


def export_one(slot):
    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_export_baseline as exporter
    import ds7_fast_baseline_adapter as baseline

    plan = json.loads(PLAN.read_text())
    validate_export_plan(plan)
    row = plan["captures"][slot]
    index = row["full_manifest_index"]
    folder = HERE / "exports" / f"{index:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    observation = folder / "observations.json"
    bank_manifest = folder / "banks/manifest.json"
    if observation.exists() or bank_manifest.exists():
        raise FileExistsError("preserve partial exports; explicit recovery required")
    document = exporter.export(row, observation, Path("/srv/bulk/leo"), Path("/var/lib/leo/tle"))
    evidence = ANALYSIS / f"{row['session_id']}.json"
    if "sha256:" + digest(evidence) != row["analysis_evidence_sha256"]:
        raise ValueError("minted analysis evidence digest mismatch")
    if document["analysis_manifest_sha256"] != json.loads(evidence.read_text())["glrt"]["metrics_manifest_sha256"]:
        raise ValueError("exported analysis manifest differs from minted evidence")
    exporter.export_banks(
        row, observation, folder / "banks", Path("/srv/bulk/leo"), Path("/var/lib/leo/tle")
    )
    paths = [observation, bank_manifest, folder / "banks/banks.npz"]
    entry = {
        "session_id": row["session_id"],
        "manifest_sha256": row["manifest_sha256"],
        "full_manifest_index": index,
        "artifacts": [
            {
                "kind": "observations" if position == 0 else "candidates",
                "path": str(path.resolve()),
                "sha256": "sha256:" + digest(path),
            }
            for position, path in enumerate(paths)
        ],
    }
    loaded = baseline.load_documents({"config": plan["config"], "inputs": [entry]})[0]
    if loaded["sample_rate_hz"] != row["sample_rate_hz"]:
        raise ValueError("sample rate mismatch")
    metadata = json.loads(bank_manifest.read_text())
    if not all(
        source["collected_utc_ns"] < loaded["start_utc_ns"] - 505_000_000_000
        for source in metadata["provider_sources"]
    ):
        raise ValueError("original bank source violates causal 505-second guard")
    result = {
        "full_manifest_index": index,
        "slot": slot,
        "input": entry,
        "tracks": len(loaded["tracks"]),
        "observations": sum(len(track["y"]) for track in loaded["tracks"]),
        "eligibility_exclusions": loaded["eligibility_exclusions"],
        "mint_analysis_match": True,
        "source_sha256": digest(__file__),
    }
    with (folder / "validated.json").open("x") as stream:
        json.dump(result, stream, indent=2)


def batch():
    plan = json.loads(PLAN.read_text())
    validate_export_plan(plan)
    for slot, row in enumerate(plan["captures"]):
        index = row["full_manifest_index"]
        receipt = HERE / f"export_{index:02d}.receipt.json"
        log = HERE / f"export_{index:02d}.log"
        if receipt.exists():
            continue
        if log.exists():
            raise RuntimeError("audit the unreceipted process before continuing")
        command = [
            "sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "180s", "nice", "-n", "19",
            PYTHON, str(Path(__file__).resolve()), "one", str(slot),
        ]
        started = time.monotonic()
        with log.open("x") as stream:
            completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        terminal = {
            "full_manifest_index": index,
            "slot": slot,
            "exit_code": completed.returncode,
            "wall_s": time.monotonic() - started,
            "command": command,
            "source_sha256": digest(__file__),
            "log_sha256": digest(log),
        }
        with receipt.open("x") as stream:
            json.dump(terminal, stream, indent=2)
        print(json.dumps(terminal), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "one":
        export_one(int(sys.argv[2]))
    elif sys.argv[1] == "batch":
        batch()
    else:
        raise ValueError(sys.argv[1])
