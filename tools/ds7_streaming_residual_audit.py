"""Stream sealed DS7 fixed-position residuals while retaining unqualified controls."""

from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path

import ds7_residual_audit as original
import numpy as np


def qualified(response):
    return (
        response.get("status") == "ok"
        and response.get("converged") is True
        and response.get("boundary_hit") is False
    )


def totals(rows):
    result = {"tracks": len(rows)}
    for key in (
        "training_observations",
        "held_observations",
        "training_log_score",
        "held_predictive_log_density",
    ):
        result[key] = sum(row[key] for row in rows)
    for role in ("training", "held"):
        count = result[role + "_observations"]
        result[role + "_rms_hz"] = float(
            np.sqrt(
                sum(row[role + "_rms_hz"] ** 2 * row[role + "_observations"] for row in rows)
                / count
            )
        )
    return result


def run(request_path, joint_path, index_path, output):
    request = json.loads(request_path.read_text())
    sessions = [row["session_id"] for row in request["inputs"]]
    index = json.loads(index_path.read_text())["responses"]
    if len(sessions) != 88 or [row["session_id"] for row in index] != sessions:
        raise ValueError("required 88-record index membership/order mismatch")
    joint, provenance = original.load_sealed_response(
        joint_path, request["unit"]["unit_id"], sessions
    )
    if request_path.resolve() != joint_path.with_name("request.json").resolve():
        raise ValueError("request must be the sealed joint request")
    joint_x = original.response_x(joint)
    if len(joint_x) != 90:
        raise ValueError("full88 joint parameter dimension mismatch")
    output.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema": "ds7-streaming-residual/v1",
        "status": "running",
        "joint_provenance": provenance,
        "index_sha256": original.digest(index_path),
        "reference_policy": "No new reference scoring; frozen model retains inherited DS6 prior.",
        "recordings": [],
    }
    for number, (row, item) in enumerate(zip(request["inputs"], index, strict=True)):
        unit = f"single-{number + 1:03}"
        independent, independent_provenance = original.load_sealed_response(
            Path(item["response_path"]), unit, [row["session_id"]]
        )
        if original.digest(Path(item["response_path"])) != item["response_sha256"]:
            raise ValueError("indexed independent response changed")
        # Verify the exact bytes before opening this one bank; never load all88 banks together.
        artifact_hashes = {}
        for artifact in row["artifacts"]:
            path = Path(artifact["path"])
            actual = original.digest(path)
            if actual != artifact["sha256"]:
                raise ValueError(f"input artifact hash mismatch: {path}")
            artifact_hashes[str(path)] = actual
        document = original.solver.load_documents({**request, "inputs": [row]})[0]
        model = original.solver.Stationary(document, request["config"])
        duration = max(max(track["times_s"]) for track in document["tracks"])
        local_joint = np.array([joint_x[0], joint_x[1], joint_x[number + 2]])
        joint_rows = [
            original.audit_track(model, track, local_joint, duration)
            for track in document["tracks"]
        ]
        control_rows = None
        if qualified(independent):
            control_x = original.response_x(independent)
            control_rows = [
                original.audit_track(model, track, control_x, duration)
                for track in document["tracks"]
            ]
        entry = {
            "unit_id": unit,
            "session_id": row["session_id"],
            "joint": totals(joint_rows),
            "independent_qualified": qualified(independent),
            "independent_status": {
                k: independent.get(k) for k in ("status", "converged", "boundary_hit")
            },
            "independent": totals(control_rows) if control_rows else None,
            "eligibility_exclusions": document["eligibility_exclusions"],
        }
        if control_rows:
            entry["joint_minus_independent_held"] = (
                entry["joint"]["held_predictive_log_density"]
                - entry["independent"]["held_predictive_log_density"]
            )
        else:
            entry["joint_minus_independent_held"] = None
        detail = {
            **entry,
            "joint_tracks": joint_rows,
            "independent_tracks": control_rows,
            "artifact_hashes": artifact_hashes,
            "independent_provenance": independent_provenance,
        }
        with (output / f"{unit}.json").open("x") as stream:
            json.dump(detail, stream, allow_nan=False)
        summary["recordings"].append(entry)
        print(
            unit, "done", "paired" if control_rows else "joint-only-unqualified-control", flush=True
        )
        del document, model, joint_rows, control_rows, detail
        gc.collect()
    summary["status"] = "complete"
    summary["joint_recordings"] = len(summary["recordings"])
    summary["paired_qualified_recordings"] = sum(
        r["independent_qualified"] for r in summary["recordings"]
    )
    with (output / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("request", "joint", "index", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.request, args.joint, args.index, args.output)


if __name__ == "__main__":
    main()
