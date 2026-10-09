"""Activate the reviewed B7 analysis overlay; never touch acquisition services."""

import hashlib
import json
import os
import shlex
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = Path("/opt/leo-b7/aa296fd94-r1")
SUFFIX = "z" * 18 + "-hard60-b7.conf"


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def verify_stage():
    receipt = json.loads((STAGE / "stage.json").read_text())
    count = 0
    for role, entry in receipt["roles"].items():
        for name, expected in entry["files"].items():
            actual = (
                "sha256:" + hashlib.sha256((STAGE / role / "src" / name).read_bytes()).hexdigest()
            )
            assert actual == expected, (role, name)
            count += 1
    for name, expected in receipt["web"].items():
        assert "sha256:" + hashlib.sha256((STAGE / name).read_bytes()).hexdigest() == expected
        count += 1
    return receipt["revision"], count


if __name__ == "__main__":
    assert os.geteuid() == 0
    assert not (HERE / "activation.json").exists(), "Preserve activation receipt"
    revision, count = verify_stage()
    protocol = json.loads(
        (HERE.parent / "2026_10_09_position_error_iter85/protocol.json").read_text()
    )
    labels = {r["member"]["inventory_label"] for r in protocol["members"]}
    rows = [json.loads(p.read_text()) for p in (HERE / "qualification").glob("*.json")]
    assert {r["member"]["inventory_label"] for r in rows} == labels
    assert all(
        len(r["comparisons"]) == 2 and all(c["passed"] for c in r["comparisons"].values())
        for r in rows
    )
    cold = json.loads((HERE / "cold.json").read_text())
    assert cold["slices"][-1]["state"] == "complete"
    units = [
        line.split()[0]
        for line in command(
            "systemctl",
            "list-units",
            "--type=service",
            "--state=running",
            "--no-legend",
            "--plain",
            "leo-adaptive-analysis-worker@*.service",
        ).splitlines()
    ]
    assert len(units) == 19, units
    units.append("leo-api.service")
    previous = {
        unit: command("systemctl", "show", unit, "-p", "Environment", "--value")
        for unit in units + ["leo-adaptive-analysis-queue.service"]
    }
    staged = json.loads((STAGE / "stage.json").read_text())
    for unit, environment in previous.items():
        role = "api" if unit == "leo-api.service" else "worker"
        path = next(
            v.split("=", 1)[1] for v in shlex.split(environment) if v.startswith("PYTHONPATH=")
        )
        assert path.split(":")[0] == staged["roles"][role]["inherited"], (
            "Concurrent selector change"
        )
    dropins = {
        Path("/etc/systemd/system/leo-adaptive-analysis-worker@.service.d")
        / SUFFIX: f"[Service]\nEnvironment=PYTHONPATH={STAGE}/worker/src\n"
        "ExecStartPre=+/usr/bin/install -d -o leo -g leo -m 0750 "
        "/srv/bulk/leo/scanner-regional-position-v3\n",
        Path("/etc/systemd/system/leo-adaptive-analysis-queue.service.d")
        / SUFFIX: f"[Service]\nEnvironment=PYTHONPATH={STAGE}/worker/src\n",
        Path("/etc/systemd/system/leo-api.service.d")
        / SUFFIX: f"[Service]\nEnvironment=PYTHONPATH={STAGE}/api/src:"
        "/opt/leo-v060-adaptive/a491b1ca7ee021e3e0e19a8c98becd2c9b1dae8b/src\n"
        "ExecStart=\n"
        f"ExecStart=/usr/bin/env PYTHONDONTWRITEBYTECODE=1 LEO_WEB_DIST={STAGE}/web/dist "
        "/opt/leo-tracker/current-api/.venv/bin/leo-api\n",
    }
    for path in dropins:
        assert not path.exists(), path
    prepared = dict(
        revision=revision,
        stage=str(STAGE),
        verified_files=count,
        started_utc=datetime.now(UTC).isoformat(),
        units=units,
        prior_environments=previous,
        dropins={str(k): v for k, v in dropins.items()},
        rollout_fraction=1.0,
        acquisition_changed=False,
    )
    (HERE / "activation-prepared.json").write_text(json.dumps(prepared, indent=2) + "\n")
    for path, value in dropins.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "--no-block", *units], check=True)
    deadline = time.monotonic() + 120
    runtime = []
    while time.monotonic() < deadline:
        runtime = []
        for unit in units:
            active = subprocess.run(
                ["systemctl", "is-active", unit], text=True, capture_output=True
            )
            if active.stdout.strip() != "active":
                break
            pid = int(command("systemctl", "show", unit, "-p", "MainPID", "--value"))
            if not pid:
                break
            try:
                env = dict(
                    item.split("=", 1)
                    for item in Path(f"/proc/{pid}/environ").read_text().split("\0")
                    if "=" in item
                )
            except FileNotFoundError:
                break
            role = "api" if unit == "leo-api.service" else "worker"
            if not env.get("PYTHONPATH", "").startswith(str(STAGE / role / "src")):
                break
            runtime.append(
                dict(
                    unit=unit,
                    pid=pid,
                    pythonpath=env["PYTHONPATH"],
                    executable=os.readlink(f"/proc/{pid}/exe"),
                )
            )
        if len(runtime) == len(units):
            break
        time.sleep(1)
    assert len(runtime) == len(units), "Activation incomplete; consult prepared rollback selectors"
    prepared.update(completed_utc=datetime.now(UTC).isoformat(), runtime=runtime)
    (HERE / "activation.json").write_text(json.dumps(prepared, indent=2) + "\n")
    print(json.dumps(dict(revision=revision, units_verified=len(runtime), rollout_fraction=1.0)))
