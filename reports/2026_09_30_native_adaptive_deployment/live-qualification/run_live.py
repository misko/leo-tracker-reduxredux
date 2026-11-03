#!/usr/bin/env python3
"""Adapted bounded live-qualification reproduction harness; not production."""

import argparse
import hashlib
import json
import math
import re
import shlex
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEPLOYMENT = HERE.parent
DEFAULT_CREDENTIAL = Path("/etc/leo/credentials/scanner-iiod-ssh-password")
DEFAULT_KNOWN_HOSTS = DEPLOYMENT / "firmware/private/192.168.1.15-v054.root.known_hosts"
REMOTE_INPUTS = Path("/mnt/glrtbench/ds9-native-comparison-20260930")
REMOTE_LOGS = Path("/mnt/glrtbench/native-adaptive/live-qualification")
MAXIMUM_AGGREGATE_SECONDS = 1560
MAXIMUM_WATCHDOG_SECONDS = 600
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
CLEANUP_PATTERN = re.compile(
    r"scanner failed: run=(-?\d+) close=(-?\d+) deactivate=(-?\d+) "
    r"radio_restore=(-?\d+) owner=(-?\d+) detector=(-?\d+)"
)
CLEANUP_FIELDS = (
    "source_close_status",
    "owner_deactivate_status",
    "radio_restore_status",
    "owner_release_status",
    "detector_destroy_status",
)


def watchdog_seconds(capture_seconds):
    hard_limit = capture_seconds + 15
    if hard_limit > MAXIMUM_WATCHDOG_SECONDS:
        raise ValueError(
            f"capture duration requires {hard_limit}s watchdog; "
            f"maximum is {MAXIMUM_WATCHDOG_SECONDS}s"
        )
    return hard_limit


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def receipt_has_zero_cleanup(receipt):
    for summary in receipt.get("summaries", []):
        if all(field in summary for field in CLEANUP_FIELDS):
            return all(summary[field] == 0 for field in CLEANUP_FIELDS)
    match = CLEANUP_PATTERN.search(receipt.get("stderr", ""))
    return match is not None and all(int(value) == 0 for value in match.groups()[1:])


def charged_seconds_for_run(row, directory=HERE):
    """Return a proof-bound charge, falling back to the original reservation."""
    reserved = row.get("reserved_seconds")
    if type(reserved) is not int or reserved < 0:
        raise ValueError("ledger reserved_seconds must be a nonnegative integer")
    charged = row.get("charged_seconds")
    evidence = row.get("finished_process_upper_bound_evidence")
    if row.get("status") != "finished" or charged is None or not isinstance(evidence, dict):
        return reserved
    try:
        if type(charged) is not int or not 0 <= charged <= reserved:
            return reserved
        if row.get("unused_reservation_released_seconds") != reserved - charged:
            return reserved
        receipt_name = evidence["receipt_path"]
        if not isinstance(receipt_name, str) or Path(receipt_name).name != receipt_name:
            return reserved
        expected_hash = evidence["receipt_sha256"]
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            return reserved
        receipt_path = directory / receipt_name
        if not receipt_path.is_file() or file_sha256(receipt_path) != expected_hash:
            return reserved
        receipt = json.loads(receipt_path.read_text())
        elapsed = evidence["host_elapsed_seconds"]
        if (
            type(elapsed) not in (int, float)
            or isinstance(elapsed, bool)
            or not math.isfinite(elapsed)
            or elapsed < 0
            or receipt.get("name") != row.get("name")
            or receipt.get("elapsed_wall_s") != elapsed
            or row.get("elapsed_wall_s") != elapsed
            or receipt.get("exit_code") != row.get("exit_code")
            or math.ceil(elapsed) != charged
            or evidence.get("no_capture_process_after_close") is not True
            or not receipt_has_zero_cleanup(receipt)
        ):
            return reserved
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return reserved
    return charged


def aggregate_charged_seconds(ledger, directory=HERE):
    return sum(charged_seconds_for_run(row, directory) for row in ledger["runs"])


def ssh_base(args):
    return [
        "sudo",
        "-n",
        "sshpass",
        "-f",
        str(args.credential_file),
        "ssh",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={args.known_hosts}",
        f"{args.user}@{args.host}",
    ]


def ssh(args, command, timeout=60):
    result = subprocess.run(
        ssh_base(args) + [command], capture_output=True, text=True, timeout=timeout
    )
    if result.returncode:
        raise RuntimeError(f"SSH command failed ({result.returncode}): {result.stderr[-2000:]}")
    return result


def radio_state(args):
    fields = {
        "frequency_hz": "iio:device0/out_altvoltage0_RX_LO_frequency",
        "source_rate_hz": "iio:device0/in_voltage_sampling_frequency",
        "capture_rate_hz": "iio:device5/in_voltage_sampling_frequency",
        "bandwidth_hz": "iio:device0/in_voltage_rf_bandwidth",
        "rx0_gain_mode": "iio:device0/in_voltage0_gain_control_mode",
        "rx1_gain_mode": "iio:device0/in_voltage1_gain_control_mode",
    }
    paths = [f"/sys/bus/iio/devices/{value}" for value in fields.values()]
    values = ssh(args, "cat " + " ".join(map(shlex.quote, paths))).stdout.splitlines()
    if len(values) != len(fields):
        raise RuntimeError("radio-state field count differs")
    return dict(zip(fields, values, strict=True))


def monitor(args):
    command = (
        "cat /proc/uptime "
        "/sys/bus/iio/devices/iio:device1/in_temp0_raw "
        "/sys/bus/iio/devices/iio:device1/in_temp0_offset "
        "/sys/bus/iio/devices/iio:device1/in_temp0_scale /proc/meminfo; "
        "for p in $(pidof leo-adaptive-scanner); do "
        "cat /proc/$p/status /proc/$p/stat; done"
    )
    return {"host_monotonic_s": time.monotonic(), "raw": ssh(args, command).stdout}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--dwell", type=int, choices=(120, 240, 360), default=120)
    parser.add_argument("--block-ms", type=int, choices=(20, 120), required=True)
    parser.add_argument("--host", default="192.168.1.15")
    parser.add_argument("--user", default="root")
    parser.add_argument("--credential-file", type=Path, default=DEFAULT_CREDENTIAL)
    parser.add_argument("--known-hosts", type=Path, default=DEFAULT_KNOWN_HOSTS)
    parser.add_argument(
        "--authorized",
        action="store_true",
        help="required acknowledgement that this invocation has live-RF authorization",
    )
    args = parser.parse_args()
    if not args.authorized:
        parser.error("--authorized is required for live capture")
    if args.seconds <= 0:
        parser.error("--seconds must be positive")

    release = json.loads((DEPLOYMENT / "release.json").read_text())
    remote = Path(release["remote_directory"])
    release_id = release["manifest"]["release_id"]
    hard_limit = watchdog_seconds(args.seconds)
    ledger_path = HERE / "budget.json"
    ledger = json.loads(ledger_path.read_text())
    if aggregate_charged_seconds(ledger, HERE) + hard_limit > min(
        ledger["maximum_aggregate_seconds"], MAXIMUM_AGGREGATE_SECONDS
    ):
        raise RuntimeError("authorized aggregate live-run budget exhausted")
    if any(row["name"] == args.name for row in ledger["runs"]):
        raise RuntimeError("run name already exists")
    if any(row["status"] == "started" for row in ledger["runs"]):
        raise RuntimeError("another live run is recorded as started")

    command = (
        f"{remote}/measure-run {hard_limit} {remote}/leo-adaptive-scanner "
        f"--capture --duration-ms {args.seconds * 1000} --maximum-visits 16384 "
        f"--active-dwell-ms {args.dwell} --block-ms {args.block_ms} "
        f"--exact-template {REMOTE_INPUTS}/lower-exact.c128 "
        f"--control-template {REMOTE_INPUTS}/lower-control.c128 "
        "--target 0 960000000 --target 1 1210000000 "
        "--target 2 1460000000 --target 3 1710000000"
    )
    before = radio_state(args)
    ledger["runs"].append(
        {
            "name": args.name,
            "reserved_seconds": hard_limit,
            "requested_seconds": args.seconds,
            "status": "started",
            "command": command,
            "release_id": release_id,
        }
    )
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    output = HERE / f"{args.name}.jsonl"
    errors = HERE / f"{args.name}.stderr"
    ssh(args, f"mkdir -p {shlex.quote(str(REMOTE_LOGS))}")
    remote_output = REMOTE_LOGS / f"{args.name}.jsonl"
    remote_errors = REMOTE_LOGS / f"{args.name}.stderr"
    remote_command = (
        f"{command} >{shlex.quote(str(remote_output))} 2>{shlex.quote(str(remote_errors))}; "
        f"status=$?; cat {shlex.quote(str(remote_output))}; "
        f'cat {shlex.quote(str(remote_errors))} >&2; exit "$status"'
    )
    samples = []
    started = time.monotonic()
    with output.open("w") as stdout, errors.open("w") as stderr:
        process = subprocess.Popen(ssh_base(args) + [remote_command], stdout=stdout, stderr=stderr)
        while True:
            try:
                code = process.wait(timeout=10)
                break
            except subprocess.TimeoutExpired:
                samples.append(monitor(args))
                if time.monotonic() - started > hard_limit + 20:
                    process.kill()
                    process.wait()
                    code = 124
                    break
    elapsed = time.monotonic() - started
    ledger["runs"][-1].update(status="finished", exit_code=code, elapsed_wall_s=elapsed)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")
    from summarize import load_records

    rows = load_records(output)
    after = radio_state(args)
    receipt = {
        "name": args.name,
        "exit_code": code,
        "elapsed_wall_s": elapsed,
        "event_count": len(rows),
        "summaries": [row for row in rows if "kind" not in row],
        "stderr": errors.read_text(),
        "raw_iq_transferred": False,
        "release_id": release_id,
        "malformed_json_lines": [],
        "radio_before": before,
        "radio_after": after,
        "radio_settings_restored": before == after,
        "monitor": samples,
        "diagnostics_written_locally_during_capture": True,
    }
    (HERE / f"{args.name}-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
