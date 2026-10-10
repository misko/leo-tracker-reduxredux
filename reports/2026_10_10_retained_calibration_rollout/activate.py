"""Select the parity-qualified recovery overlay for adaptive workers and queue."""

import hashlib
import json
import os
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = Path("/opt/leo-b7/a620e14f3-retained-r1")
BASE = Path("/opt/leo-b7/88e231eb1-r1/worker/src")
REVISION = "a620e14f314c5500de1d3e19a0b4aa2a68a13825"
SUFFIX = "z" * 24 + "-retained-calibration.conf"
WORKER_UNIT = "leo-adaptive-analysis-worker@.service"
QUEUE_UNIT = "leo-adaptive-analysis-queue.service"
QUEUE_TIMER = "leo-adaptive-analysis-queue.timer"


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def effective_path(unit):
    environment = command("systemctl", "show", unit, "-p", "Environment", "--value")
    values = [
        value.split("=", 1)[1]
        for value in shlex.split(environment)
        if value.startswith("PYTHONPATH=")
    ]
    if len(values) != 1:
        raise ValueError(f"ambiguous source selector: {unit}")
    return values[0].split(":")[0]


def verify_stage():
    receipt = json.loads((STAGE / "stage.json").read_text())
    if receipt["revision"] != REVISION or receipt["inherited"] != str(BASE):
        raise ValueError("unexpected immutable stage")
    for name, expected in receipt["files"].items():
        path = STAGE / "worker/src" / name
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"staged source changed: {name}")
    return len(receipt["files"])


def workers():
    lines = command(
        "systemctl",
        "list-units",
        "--type=service",
        "--state=running",
        "--no-legend",
        "--plain",
        "leo-adaptive-analysis-worker@*.service",
    )
    units = sorted(line.split()[0] for line in lines.splitlines())
    expected = [0, 2, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 21, 22, 23, 24, 25]
    if units != sorted(f"leo-adaptive-analysis-worker@{number}.service" for number in expected):
        raise ValueError("active worker inventory changed")
    return units


def active_on_stage(units):
    for unit in units:
        state = subprocess.run(
            ["systemctl", "is-active", unit], capture_output=True, text=True
        ).stdout.strip()
        if state != "active":
            return False
        if effective_path(unit) != str(STAGE / "worker/src"):
            return False
        pid = int(command("systemctl", "show", unit, "-p", "MainPID", "--value"))
        if not pid:
            return False
        environment = Path(f"/proc/{pid}/environ").read_bytes()
        if b"PYTHONPATH=" + str(STAGE / "worker/src").encode() not in environment:
            return False
    return True


def main():
    if os.geteuid() != 0 or (HERE / "activation.json").exists():
        raise PermissionError("root and a fresh activation receipt are required")
    parity = json.loads((HERE / "parity.json").read_text())
    if (
        parity["status"] != "passed"
        or parity["stage_revision"] != REVISION
        or len(parity["comparisons"]) != 6
        or parity["maximum_score_delta"] > 1e-5
        or parity["maximum_vector_delta"] > 1e-6
    ):
        raise ValueError("staged ac11 numerical parity is not qualified")
    file_count = verify_stage()
    units = workers()
    all_units = [*units, QUEUE_UNIT]
    previous = {unit: effective_path(unit) for unit in all_units}
    if set(previous.values()) != {str(BASE)}:
        raise ValueError("adaptive selectors changed concurrently")
    dropins = {
        Path("/etc/systemd/system") / (name + ".d") / SUFFIX: (
            f"[Service]\nEnvironment=PYTHONPATH={STAGE}/worker/src\n"
        )
        for name in (WORKER_UNIT, QUEUE_UNIT)
    }
    if any(path.exists() for path in dropins):
        raise FileExistsError("recovery selector already exists")
    timer_active = command("systemctl", "is-active", QUEUE_TIMER) == "active"
    receipt = dict(
        revision=REVISION,
        stage=str(STAGE),
        verified_files=file_count,
        started_utc=datetime.now(UTC).isoformat(),
        workers=units,
        previous_selectors=previous,
        queue_timer_was_active=timer_active,
        dropins=[str(path) for path in dropins],
        acquisition_changed=False,
    )
    (HERE / "activation-prepared.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if timer_active:
        subprocess.run(["systemctl", "stop", QUEUE_TIMER], check=True)
    subprocess.run(["systemctl", "stop", QUEUE_UNIT], check=True)
    try:
        for path, content in dropins.items():
            path.write_text(content)
            path.chmod(0o644)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", "--no-block", *units], check=True)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not active_on_stage(units):
            time.sleep(2)
        if not active_on_stage(units):
            raise TimeoutError("adaptive workers did not all load the new overlay")
        if effective_path(QUEUE_UNIT) != str(STAGE / "worker/src"):
            raise ValueError("adaptive queue did not load the new selector")
        if timer_active:
            subprocess.run(["systemctl", "start", QUEUE_TIMER], check=True)
        subprocess.run(["systemctl", "start", QUEUE_UNIT], check=True)
    except Exception:
        for path in dropins:
            path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", "--no-block", *units], check=True)
        if timer_active:
            subprocess.run(["systemctl", "start", QUEUE_TIMER], check=True)
        raise
    receipt.update(
        completed_utc=datetime.now(UTC).isoformat(),
        effective_selectors={unit: effective_path(unit) for unit in all_units},
        queue_timer_active=command("systemctl", "is-active", QUEUE_TIMER) == "active",
    )
    (HERE / "activation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(dict(status="active", workers=len(units), stage=str(STAGE))))


if __name__ == "__main__":
    main()
