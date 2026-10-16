"""Pin DS20 coverage and inspect native all/low/high views without fitting or truth."""

import argparse
import hashlib
import json
import runpy
import signal
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from leo.application.regional_position_inputs import prepare_position_windows

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = Path("/srv/bulk/leo-dev/leo-ds20-eight-channel/reports/2026_10_12_ds20_eight_channel")
ADAPTER = Path("/opt/leo-fast-auto/20261011-r3/bin/fast_scan_standard_pipeline.py")
OUTPUT = ROOT / "reports/2026_10_12_ds20_channel_calibration"


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


@contextmanager
def bounded(seconds):
    original = signal.getsignal(signal.SIGALRM)

    def expired(*_):
        raise TimeoutError("native view preparation exceeded its 60-second case bound")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original)


def freeze(authority, output):
    manifest = json.loads((authority / "manifest.json").read_bytes())
    protocol = json.loads((authority / "protocol.json").read_bytes())
    assignments = {a["recording_id"]: a["split"] for a in protocol["assignments"]}
    members = []
    for member in manifest["members"]:
        entry = {
            "session_id": member["session_id"],
            "recording_id": member["recording_id"],
            "case_id": member["case_id"],
            "role": assignments[member["recording_id"]],
            "input": None,
            "input_reason": None,
        }
        inputs = member["tracking_inputs"]
        if inputs:
            entry["input"] = inputs[0]
        else:
            recovery = authority / "recovery" / member["session_id"]
            receipt = recovery / "recovery-receipt.json"
            if receipt.exists():
                value = json.loads(receipt.read_bytes())
                entry["input"] = {
                    "path": str(recovery / "tracking-input.json"),
                    "sha256": value["tracking_input_sha256"],
                    "recovery_receipt": str(receipt),
                    "recovery_receipt_sha256": digest(receipt),
                }
            else:
                entry["input_reason"] = "No original or sealed recovered tracking input"
        members.append(entry)
    assert len(members) == len({m["session_id"] for m in members}) == 18
    membership = {
        "dataset": "DS20",
        "authority": str(authority / "manifest.json"),
        "authority_sha256": digest(authority / "manifest.json"),
        "partition_authority": str(authority / "protocol.json"),
        "partition_sha256": digest(authority / "protocol.json"),
        "adapter": str(ADAPTER),
        "adapter_sha256": digest(ADAPTER),
        "members": members,
        "roles": dict(Counter(m["role"] for m in members)),
        "views": {"all": list(range(1, 9)), "low": list(range(1, 5)), "high": list(range(5, 9))},
        "scope": (
            "Frozen exposed DS20 corpus, retaining original whole-recording roles "
            "and every failure. "
            "No reference values used in inventory or inference."
        ),
    }
    path = output / "membership.json"
    if path.exists():
        if json.loads(path.read_bytes()) != membership:
            raise ValueError("Frozen DS20 membership or authorities changed")
    else:
        write(path, membership)
    return membership


def census(member, loader, views):
    begun = time.monotonic()
    result = {"session_id": member["session_id"], "role": member["role"], "views": {}}
    receipt = member["input"]
    if receipt is None:
        result.update(state="input-unavailable", reason=member["input_reason"])
        return result
    path = Path(receipt["path"])
    if digest(path) != receipt["sha256"]:
        raise ValueError("Pinned DS20 input changed")
    source = loader(json.loads(path.read_bytes()))
    if source.session_id != member["session_id"]:
        raise ValueError("DS20 input session differs")
    result.update(
        input_sha256=source.input_manifest_sha256,
        analysis_sha256=source.analysis_manifest_sha256,
        capture_qualified=source.qualified,
    )
    full_rows = None
    with bounded(60):
        for name, channels in views.items():
            filtered = replace(
                source, probes=tuple(p for p in source.probes if p.channel in channels)
            )
            row = {
                "channels": channels,
                "probes": len(filtered.probes),
                "receiver_probes": dict(Counter(p.receiver_id for p in filtered.probes)),
            }
            try:
                prepared = prepare_position_windows(filtered)
                obs = prepared.observations
                row.update(
                    state="prepared",
                    windows=len(obs.window_ids),
                    windows_by_channel=dict(Counter(map(int, obs.channel))),
                    windows_by_receiver=dict(Counter(map(int, obs.receiver))),
                    bootstrap_tracks=len(prepared.bootstrap_tracks),
                    evidence_sha256=prepared.evidence_sha256,
                )
                if name == "all":
                    full_rows = set(obs.window_ids)
                elif full_rows is not None and not set(obs.window_ids) <= full_rows:
                    raise ValueError("Channel filter changed physical window identity")
            except ValueError as error:
                # Persist the complete reason; no trial is silently removed.
                row.update(state="unavailable", reason=f"{type(error).__name__}: {error}")
            result["views"][name] = row
    result.update(state="census-complete", elapsed_s=time.monotonic() - begun)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "census"))
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    membership = freeze(args.authority, args.output)
    if args.command == "freeze":
        print(json.dumps({"members": len(membership["members"]), "roles": membership["roles"]}))
        return
    loader = runpy.run_path(str(ADAPTER))["load_tracking_input"]
    rows = []
    for member in membership["members"]:
        path = args.output / "local/census" / (member["session_id"] + ".json")
        if path.exists():
            row = json.loads(path.read_bytes())
        else:
            try:
                row = census(member, loader, membership["views"])
            except (ValueError, TimeoutError) as error:
                row = {
                    "session_id": member["session_id"],
                    "role": member["role"],
                    "state": "census-failed",
                    "reason": f"{type(error).__name__}: {error}",
                }
            write(path, row)
        rows.append(row)
        write(
            args.output / "coverage.json",
            {
                "dataset": "DS20",
                "total_members": 18,
                "reviewed": len(rows),
                "membership_sha256": digest(args.output / "membership.json"),
                "rows": rows,
                "algorithm_status": "Baseline support census; stable combined algorithm unproven.",
            },
        )
        print(
            json.dumps(
                {
                    "session_id": row["session_id"],
                    "reviewed": len(rows),
                    "state": row["state"],
                    "views": {k: v["state"] for k, v in row.get("views", {}).items()},
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
