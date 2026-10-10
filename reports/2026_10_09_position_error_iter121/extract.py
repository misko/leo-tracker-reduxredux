"""Export sealed selected endpoints only; never compute reference errors."""

import hashlib
import json
import runpy
from pathlib import Path

import numpy as np

from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def position_only(operation, prior):
    if operation is None:
        return None
    fit = operation["fit"]
    latlon = coordinates(RegionalPrior(**prior), np.asarray(fit["vector"])[:2])
    return {
        "latlon": list(latlon),
        "qualified": bool(fit.get("converged", False)),
        "qualification_reason": fit.get("stop_reason"),
        "selection": operation.get("selection"),
    }


def main():
    base = ROOT / "reports/2026_10_09_position_error_iter107"
    protocol = json.loads((base / "protocol.json").read_text())
    full = json.loads((base / "FULL193_COMPLETE_SNAPSHOT.json").read_text())
    assert len(full["rows"]) == 193 and all(r["paired_terminal"] for r in full["rows"])
    report = runpy.run_path(str(base / "report.py"))
    historical_path = ROOT / "reports/2026_10_09_position_error_iter85/protocol.json"
    newer_path = ROOT / "reports/2026_10_09_position_error_iter89/local/manifest.json"
    historical = json.loads(historical_path.read_text())["members"]
    newer = json.loads(newer_path.read_text())["captures"]
    times = {m["member"]["session_id"]: m["member"]["capture_start_utc_ns"] for m in historical}
    times.update({m["session_id"]: m["capture_start_utc_ns"] for m in newer})
    bindings = {
        str(p.relative_to(ROOT)): sha(p)
        for p in (
            base / "protocol.json",
            base / "FULL193_COMPLETE_SNAPSHOT.json",
            historical_path,
            newer_path,
            base / "report.py",
            Path(__file__),
        )
    }
    output = []
    for member in protocol["members"]:
        label = report["member_label"](member)
        records, hashes = report["phase_receipts"](
            base / "results" / label, sha(base / "protocol.json")
        )
        assert report["paired_terminal"](records), label
        for path, digest in hashes.items():
            key = str(Path(path).relative_to(ROOT))
            assert full["receipt_sha256"][path] == digest, key
            bindings[key] = digest
        # Public document port verifies frozen source identity; filter to prior
        # immediately. Reference values are never accessed or copied.
        prior = report["evaluation_document"](member)["configuration"]["prior"]
        source_identity = hashlib.sha256(
            json.dumps(prior, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        output.append(
            {
                "label": label,
                "dataset": member.get("dataset", member["member"].get("dataset")),
                "session_id": member["member"]["session_id"],
                "input_manifest_sha256": member["member"].get("recording_manifest_sha256"),
                "capture_start_utc_ns": times[member["member"]["session_id"]],
                "source_bindings_sha256": hashlib.sha256(
                    json.dumps(member["sources"], sort_keys=True).encode()
                ).hexdigest(),
                "prior_sha256": source_identity,
                "phase": "candidate",
                "status": records["candidate"]["status"],
                "arms": {
                    a: position_only(records["candidate"].get("operational", {}).get(a), prior)
                    for a in ("fitted-c", "zero-c")
                },
            }
        )
    payload = {
        "scope": "Inference-only sealed ordinary selected endpoints; conditional stationary replay not evaluated",
        "count": 193,
        "source_sha256": bindings,
        "members": output,
        "io_cost": "unmeasured; no numerical fits or recording reconstruction",
    }
    destination = HERE / "selected-positions.json"
    with destination.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
