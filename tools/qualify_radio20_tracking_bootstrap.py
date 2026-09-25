"""Run a bounded, saved-IQ ARM qualification on the explicitly bound radio .20.

This operator command claims the normal capture lease and PPU lock. It stages
only a benchmark and fixtures in RAM, never starts RX or changes firmware, and
distinguishes numerical replay completion from readiness for live tracking.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import shlex
import subprocess
import tarfile
import time
from contextlib import ExitStack
from pathlib import Path

HOST = "192.168.1.20"
SERIAL = "1040005e0b100007100010000bf33a5d4d"
FIRMWARE = "v0.49-plutoplus-spf-iq-direct-async-v4"
SCOPE = "full_resolver_catchup_saved_iq_no_iio"
PAYLOAD_NAMES = ("benchmark", "records", "anchors", "libfftw3.so.3")

ATTEST = r"""set -eu
emit() { printf '%s=%s\n' "$1" "$2"; }
emit serial "$(cat /sys/kernel/config/usb_gadget/composite_gadget/strings/0x409/serialnumber)"
emit firmware "$(awk '$1 == "device-fw" {print $2; exit}' /opt/VERSIONS)"
emit boot_id "$(cat /proc/sys/kernel/random/boot_id)"
emit fit_partition_sha256 "$(sha256sum /dev/mtdblock3 | awk '{print $1}')"
phy=''
for d in /sys/bus/iio/devices/iio:device*; do
  name=$(cat "$d/name")
  emit "device_${d##*:}" "$name"
  if test -f "$d/buffer/enable"; then emit "buffer_${d##*:}" "$(cat "$d/buffer/enable")"; fi
  if test "$name" = ad9361-phy; then phy=$d; fi
  for a in "$d"/schedule_* "$d"/tracking_*; do
    if test -f "$a"; then emit "capability_${d##*:}_${a##*/}" present; fi
  done
done
test -n "$phy"
for a in in_voltage_sampling_frequency in_voltage_rf_bandwidth \
  out_altvoltage0_RX_LO_frequency out_altvoltage1_TX_LO_powerdown \
  in_voltage0_hardwaregain in_voltage1_hardwaregain; do
  emit "$a" "$(cat "$phy/$a")"
done
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_attestation(text: str) -> dict[str, str]:
    fields = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key in fields:
            raise ValueError("malformed or duplicate radio attestation")
        fields[key] = value
    if fields.get("serial") != SERIAL or fields.get("firmware") != FIRMWARE:
        raise ValueError("radio serial or resident firmware differs")
    if not re.fullmatch(r"[0-9a-f-]{36}", fields.get("boot_id", "")):
        raise ValueError("missing boot identity")
    if not re.fullmatch(r"[0-9a-f]{64}", fields.get("fit_partition_sha256", "")):
        raise ValueError("missing firmware partition hash")
    buffers = [v for k, v in fields.items() if k.startswith("buffer_")]
    if not buffers or any(v != "0" for v in buffers):
        raise ValueError("radio has an active buffer")
    if fields.get("out_altvoltage1_TX_LO_powerdown") != "1":
        raise ValueError("TX LO is not powered down")
    return fields


def assess(result: dict) -> dict:
    """Audit every case, including unsuccessful startup and control cases."""
    if result.get("scope") != SCOPE:
        raise ValueError("wrong benchmark scope")
    rows = result.get("cases")
    if not isinstance(rows, list) or len(rows) != 14:
        raise ValueError("the complete frozen 14-case cohort is required")
    plan = result.get("plan_us")
    if type(plan) not in (int, float) or not math.isfinite(plan) or plan <= 0:
        raise ValueError("invalid FFT planning time")
    ready, controls, unsupported = [], [], []
    for index, row in enumerate(rows):
        if type(row.get("case")) is not int or row["case"] != index:
            raise ValueError("missing, reordered or duplicated case")
        if type(row.get("acquisition_supported")) is not int or row[
            "acquisition_supported"
        ] not in (0, 1):
            raise ValueError("invalid acquisition disposition")
        for key in ("resolver_us", "total_us"):
            value = row.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("invalid measured latency")
        if not row["resolver_us"] < row["total_us"] < 4_000_000:
            raise ValueError("invalid processing-time accounting")
        if type(row.get("past_jobs")) is not int or not 8 <= row["past_jobs"] <= 200:
            raise ValueError("invalid catch-up work accounting")
        if row.get("status") == 2:
            if row.get("failure") != 0:
                raise ValueError("failed work cannot authorize a handoff")
            start = row.get("handoff", {}).get("start")
            available = row.get("available_through")
            if type(start) is not int or type(available) is not int or start < available + 2500:
                raise ValueError("stale handoff")
            (ready if row["acquisition_supported"] else controls).append(index)
        elif row.get("status") == -1 and row.get("failure") in (3, 4):
            if row["acquisition_supported"]:
                unsupported.append(index)
        else:
            raise ValueError("unaccounted terminal status")
    accepted = sum(row["acquisition_supported"] for row in rows)
    if (
        accepted != 8
        or result.get("ready_cases") != len(ready) + len(controls)
        or result.get("control_ready_cases") != len(controls)
    ):
        raise ValueError("cohort or aggregate counts differ")
    return dict(
        accepted_acquisition_cases=accepted,
        control_cases=len(rows) - accepted,
        ready_signal_cases=ready,
        unsupported_signal_cases=unsupported,
        ready_control_cases=controls,
        baseline_reproduced=ready == [1, 2, 3] and not controls,
        all_accepted_cases_handed_off=not unsupported and not controls,
        resolver_ms=[row["resolver_us"] / 1000 for row in rows],
        ready_total_ms=[rows[index]["total_us"] / 1000 for index in ready],
        live_tracking_qualified=False,
        excluded=[
            "live acquisition",
            "DMA ingestion",
            "hardware submission",
            "sustained feedback",
            "physical accuracy",
            "scanning",
        ],
    )


def payload(manifest: dict) -> dict[str, bytes]:
    entries = manifest["payload"]
    if set(entries) != set(PAYLOAD_NAMES):
        raise ValueError("unexpected deployment payload")
    blobs = {}
    for name, entry in entries.items():
        path = Path(entry["path"])
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("payload must be an absolute regular file")
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("oversized payload")
        data = path.read_bytes()
        if digest(data) != entry["sha256"]:
            raise ValueError("payload identity changed")
        blobs[name] = data
    for name, sha in manifest["source_sha256"].items():
        if digest(Path(name).read_bytes()) != sha:
            raise ValueError("compiled source identity changed")
    return blobs


def archive(blobs: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for name, data in blobs.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o700 if name == "benchmark" else 0o600
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "output", "password-file", "known-hosts", "deployment-receipt"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    blobs = payload(json.loads(args.manifest.read_text()))
    deployment = json.loads(args.deployment_receipt.read_text())
    if (
        deployment.get("outcome") != "success"
        or deployment.get("returned_serial") != SERIAL
        or deployment.get("returned_firmware") != FIRMWARE
        or deployment["plan"]["host"] != HOST
        or digest(args.known_hosts.read_bytes())
        != deployment["host_key_rotation"]["replacement_known_hosts_sha256"]
    ):
        raise ValueError("pinned SSH identity does not match the deployment receipt")
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(
        scope=SCOPE,
        host=HOST,
        serial=SERIAL,
        started_utc_ns=time.time_ns(),
        manifest_sha256=digest(args.manifest.read_bytes()),
        rf_collection=False,
        firmware_written=False,
        status="started",
        temporary_files_removed=False,
    )
    ssh = [
        "sshpass",
        "-f",
        str(args.password_file),
        "ssh",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(args.known_hosts),
        "-o",
        "ConnectTimeout=5",
        "root@" + HOST,
    ]

    def run(command, data=None, timeout=40):
        result = subprocess.run(ssh + [command], input=data, capture_output=True, timeout=timeout)
        if result.returncode:
            (args.output / "failed-command-stdout.txt").write_bytes(result.stdout)
            (args.output / "failed-command-stderr.txt").write_bytes(result.stderr)
            raise RuntimeError(
                f"radio command exited {result.returncode}: "
                f"{result.stderr.decode(errors='replace')}"
            )
        return result.stdout.decode()

    # Public ownership ports; no application private storage or radio adapters.
    from pluto_plus.radio_lock import acquire_radio_lock

    from leo.acquisition.authority import CaptureTaskKind, LocalCaptureAuthority, RadioResource

    owner = LocalCaptureAuthority(
        Path("/srv/bulk/leo/control"), (RadioResource("radio_pluto_5d4d", SERIAL, "ip:" + HOST),)
    )
    remote = None
    try:
        with ExitStack() as stack:
            stack.enter_context(
                owner.claim(
                    ("radio_pluto_5d4d",),
                    task_id="radio20-tracking-bootstrap-qualification",
                    task_kind=CaptureTaskKind.QUALIFICATION,
                )
            )
            stack.enter_context(acquire_radio_lock(SERIAL))
            try:
                report["before"] = parse_attestation(run("sh -s", ATTEST.encode()))
                remote = run("mktemp -d /tmp/leo-tracking-qualification.XXXXXX").strip()
                if not re.fullmatch(r"/tmp/leo-tracking-qualification\.[A-Za-z0-9]{6}", remote):
                    remote = None
                    raise ValueError("unexpected remote staging directory")
                report["remote_directory"] = remote
                run("tar -C " + shlex.quote(remote) + " -xf -", archive(blobs))
                checks = "".join(
                    f"{digest(data)}  {remote}/{name}\n" for name, data in blobs.items()
                )
                report["remote_hash_verification"] = run("sha256sum -c", checks.encode())
                print("Running 14 saved-IQ cases on radio .20 ARM; no RF started", flush=True)
                output = run(
                    "env LD_LIBRARY_PATH="
                    + shlex.quote(remote)
                    + " "
                    + shlex.quote(remote + "/benchmark")
                    + " "
                    + shlex.quote(remote + "/records")
                    + " "
                    + shlex.quote(remote + "/anchors"),
                    timeout=55,
                )
                (args.output / "arm-output.json").write_text(output)
                report["assessment"] = assess(json.loads(output))
                report["after"] = parse_attestation(run("sh -s", ATTEST.encode()))
                if report["before"] != report["after"]:
                    raise ValueError("radio state changed during the saved-IQ benchmark")
                report["status"] = (
                    "replay_verified"
                    if report["assessment"]["baseline_reproduced"]
                    else "replay_differs"
                )
            finally:
                if remote:
                    run(
                        "rm -f -- " + " ".join(shlex.quote(remote + "/" + n) for n in PAYLOAD_NAMES)
                    )
                    run("rmdir " + shlex.quote(remote))
                    report["temporary_files_removed"] = True
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report["finished_utc_ns"] = time.time_ns()
        (args.output / "receipt.json").write_text(
            json.dumps(report, indent=2, allow_nan=False) + "\n"
        )
    print(json.dumps(dict(status=report["status"], assessment=report["assessment"])))
    return 0 if report["status"] == "replay_verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
