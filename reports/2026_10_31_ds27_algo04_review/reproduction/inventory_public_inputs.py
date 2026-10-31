"""Freeze public fast GLRT and ALGO02 availability without scientific or GPS selection."""

import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from leo.storage.fast_graph_position import FastGraphPositionStore


def sha(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identities(member):
    return {
        v
        for v in (member["recording_id"], member.get("session_id"), *member.get("session_ids", []))
        if v
    }


def choose_export(candidates):
    """Prefer verified completed production jobs, retaining other public inputs."""
    return (
        min(candidates, key=lambda row: (not row["qualified_completed_ALGO02"], row["job_id"]))
        if candidates
        else None
    )


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main(args):
    manifest = json.loads(args.manifest.read_text())
    manifest_hash = sha(args.manifest)
    if manifest["dataset_id"] != "DS27":
        raise ValueError("DS27 immutable membership required")
    fast = [m for m in manifest["members"] if m["recording_format"] == "short_window_iq_recording"]
    by_session = {}
    for member in fast:
        for identity in identities(member):
            by_session.setdefault(identity, []).append(member["dataset_label"])
    store = FastGraphPositionStore(args.bulk_root)
    matched = []
    errors = []
    read_errors = []
    checked = 0
    began = time.time_ns()
    for job in store.inputs():
        checked += 1
        path = Path(job["input_path"])
        try:
            document = json.loads(path.read_text())
            source = document.get("source", document)
            session = source["session_id"]
        except (PermissionError, OSError) as error:
            # Missing privileges must never masquerade as unavailable GLRT.
            read_errors.append(dict(path=str(path), error=f"{type(error).__name__}: {error}"))
            continue
        except (KeyError, ValueError, TypeError) as error:
            errors.append(dict(path=str(path), error=f"{type(error).__name__}: {error}"))
            continue
        if session not in by_session:
            continue
        if sha(path) != job["input_sha256"]:
            raise ValueError("Public tracking input changed during availability inventory")
        status = store.status(job["job_id"])
        row = {
            key: job[key]
            for key in ("job_id", "run_id", "model_version", "input_path", "input_sha256")
        }
        row.update(
            session_id=session,
            cases=sorted(by_session[session]),
            state=(status or {}).get("state", "unavailable"),
            updated_utc_ns=(status or {}).get("updated_utc_ns"),
            sample_rate_hz=source["sample_rate_hz"],
            qualified_completed_ALGO02=False,
        )
        if row["state"] == "complete":
            try:
                terminal, receipt = store.terminal(job)
                row["qualified_completed_ALGO02"] = terminal["state"] == "complete"
                row["terminal_receipt"] = receipt
            except (PermissionError, OSError) as error:
                read_errors.append(dict(path=str(path), error=f"{type(error).__name__}: {error}"))
            except (ValueError, KeyError, TypeError) as error:
                row["terminal_validation_failure"] = f"{type(error).__name__}: {error}"
        matched.append(row)
    if read_errors:
        write(args.output / "public-input-permission-errors.json", read_errors)
        raise PermissionError(
            "Availability census had read errors; no incomplete availability map published"
        )
    rows = []
    for member in fast:
        candidates = [r for r in matched if member["dataset_label"] in r["cases"]]
        selected = choose_export(candidates)
        row = dict(
            case=member["dataset_label"],
            case_id=member["case_id"],
            recording_id=member["recording_id"],
            recording_format=member["recording_format"],
            sample_rates_hz=member["sample_rates_hz"],
            recording_state=member["recording_state"],
            status="exported" if selected else "unavailable",
            candidate_public_inputs=len(candidates),
        )
        if selected:
            row.update({key: value for key, value in selected.items() if key != "cases"})
            row["status"] = "exported"
        else:
            row["reason"] = "no_existing_public_GLRT_input"
        rows.append(row)
    completed = [r for r in matched if r["qualified_completed_ALGO02"]]
    common = dict(
        dataset_id="DS27",
        dataset_manifest_sha256=manifest_hash,
        availability_started_utc_ns=began,
        availability_completed_utc_ns=time.time_ns(),
        snapshot_atomic=False,
        all_fast_cases_retained=True,
        acquisition_membership_uses_no_scientific_outcomes=True,
        GPS_used=False,
        IQ_payloads_read=False,
        new_RF=False,
    )
    write(
        args.output / "input-availability.json",
        dict(
            **common,
            rows=rows,
            fast_cases=len(rows),
            fast_cases_with_public_GLRT=sum(r["status"] == "exported" for r in rows),
            fast_cases_with_completed_ALGO02=sum(
                r.get("qualified_completed_ALGO02", False) for r in rows
            ),
            ALGO02_state_counts=dict(Counter(r.get("state", "unavailable") for r in rows)),
            public_inputs_checked=checked,
            malformed_unrelated_public_inputs=errors,
        ),
    )
    write(args.output / "public-input-map.json", dict(**common, rows=rows))
    # List form intentionally matches the existing generic evaluator's public-map port.
    write(args.output / "completed-algo02-job-map.json", completed)
    paths = [
        args.output / name
        for name in (
            "input-availability.json",
            "public-input-map.json",
            "completed-algo02-job-map.json",
        )
    ]
    write(
        args.output / "input-availability-seal.json",
        dict(
            dataset_manifest_sha256=manifest_hash,
            source_sha256=sha(Path(__file__)),
            files={str(path): sha(path) for path in paths},
            no_GPS=True,
        ),
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in json.loads(
                    (args.output / "input-availability.json").read_text()
                ).items()
                if key not in ("rows", "malformed_unrelated_public_inputs")
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    main(parser.parse_args())
