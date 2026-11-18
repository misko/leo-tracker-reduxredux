"""Preserve externally interrupted attempts and resume an unchanged frozen campaign.

Completed outcomes are never rerun. Interrupted attempts become explicit failed
coverage outcomes; their original records and partial artifact hashes are saved.
No interrupted attempt supplies scientific results or complete timing data.
"""

import argparse
import copy
import fcntl
import importlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def active_workers(request_path):
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        if b"worker" in arguments and os.fsencode(request_path) in arguments:
            found.append(int(entry.name))
    return found


def recover_interrupted(api, manifest, recovery_root, *, reason, stopped_utc=None):
    output = api.bulk_output(manifest["output"])
    recovery_root = api.bulk_output(recovery_root)
    recovered = []
    with (output / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for assignment in manifest["schedule"]:
            for role in manifest["roles"]:
                path = output / (assignment["case"] + "-r" + str(assignment["repetition"]))
                path /= role + "-execution.json"
                if not path.exists():
                    continue
                original = api.ev.read(path)
                if original["status"] != "started":
                    continue
                request = api.worker_request(manifest, assignment, role)
                if (request is None or original["role"] != role or
                        original["request_sha256"] != api.ev.digest(request)):
                    raise ValueError("Interrupted request binding differs: " + str(path))
                destination = Path(request["job"]["output_root"])
                request_path = destination / "experimental-request.json"
                if api.ev.read(request_path) != request:
                    raise ValueError("Interrupted worker request differs: " + str(path))
                if active_workers(request_path):
                    raise RuntimeError("Interrupted worker is still running: " + str(path))
                if any((destination / name).exists() for name in
                       ("worker-result.json", "experimental-evidence.zip")):
                    raise RuntimeError(
                        "Possible completed evidence requires inspection: " + str(path))
                evidence_path = recovery_root / path.parent.name / (role + "-interruption.json")
                if evidence_path.exists():
                    raise ValueError("Existing interruption evidence must be preserved")
                partial = {str(p): api.ev.file_digest(p) for p in sorted(destination.rglob("*"))
                           if p.is_file()}
                evidence = dict(original_record=original, original_record_path=str(path),
                                original_record_sha256=api.ev.file_digest(path),
                                partial_artifacts=partial, reason=reason,
                                external_stop_utc=stopped_utc, recovered_host=api.host(),
                                inference_rerun=False,
                                interpretation=("external interruption; "
                                                "no scientific or timing result"))
                api.write(evidence_path, evidence)
                record = copy.deepcopy(original)
                wall = None
                if stopped_utc:
                    began = datetime.fromisoformat(original["before"]["utc"].replace("Z", "+00:00"))
                    stopped = datetime.fromisoformat(stopped_utc.replace("Z", "+00:00"))
                    wall = max(0, (stopped - began).total_seconds())
                record.update(status="failed", after=api.host(),
                              process=dict(status="externally_interrupted", returncode=None,
                                           wall_seconds=wall, cpu_seconds=None, cpu_complete=False),
                              interruption=dict(reason=reason, external_stop_utc=stopped_utc,
                                                evidence_path=str(evidence_path),
                                                evidence_sha256=api.ev.file_digest(evidence_path),
                                                inference_rerun=False,
                                                timing_eligible=False))
                api.validate_record(manifest, assignment, role, record)
                api.write(path, record)
                recovered.append(str(path))
    return recovered


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--recovery-root", type=Path, required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--stopped-utc")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--reserve-gib", type=float, default=100)
    args = parser.parse_args(argv)
    campaign = json.loads(args.campaign.read_text())
    sys.path.insert(0, str(Path(campaign["runner"]).parent))
    coordinator = importlib.import_module("run_accuracy_repair_campaign")
    if Path(coordinator.__file__).resolve() != Path(campaign["runner"]).resolve():
        raise ValueError("Recovery imported a different frozen coordinator")
    manifest = coordinator.check_plan(campaign)
    recovered = recover_interrupted(coordinator.repair, manifest, args.recovery_root,
                                    reason=args.reason, stopped_utc=args.stopped_utc)
    print(json.dumps(dict(interrupted_outcomes_preserved=recovered,
                          frozen_campaign=str(args.campaign), rerun=False)), flush=True)
    if args.run:
        return coordinator.run(args.campaign, reserve_gib=args.reserve_gib)
    coordinator.save_reports(manifest, campaign)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
