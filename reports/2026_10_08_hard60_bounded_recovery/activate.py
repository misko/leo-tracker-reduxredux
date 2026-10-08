"""Select the qualified analysis-only overlay, preserving acquisition and capacity.

Run as root after reviewing qualification. Rollback removes only the three new
drop-ins listed in the receipt, reloads systemd and restarts those same units.
"""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def main(destination):
    report = Path(destination)
    stage = Path("/opt/leo-hard60/7d296d36d-r1")
    inventory = json.loads((stage / "stage.json").read_text())
    assert inventory["revision"] == "7d296d36d733a18fbc4ec28c63dc579ef2f7f136"
    count = 0
    for role, receipt in inventory["roles"].items():
        for name, expected in receipt["files"].items():
            path = stage / role / "src" / name
            assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == expected, path
            count += 1
    for name, expected in inventory["web"].items():
        assert "sha256:" + hashlib.sha256((stage / name).read_bytes()).hexdigest() == expected
        count += 1
    workers = command(
        "systemctl",
        "list-units",
        "--state=active",
        "--no-legend",
        "--plain",
        "leo-adaptive-analysis-worker@*.service",
    )
    units = sorted(line.split()[0] for line in workers.splitlines())
    expected = [0, 2, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18, 21, 22, 23, 24, 25]
    assert units == sorted(f"leo-adaptive-analysis-worker@{n}.service" for n in expected)
    units.append("leo-api.service")
    worker_environment = f"[Service]\nEnvironment=PYTHONPATH={stage}/worker/src\n"
    selectors = {
        "leo-adaptive-analysis-worker@.service": worker_environment,
        "leo-adaptive-analysis-queue.service": worker_environment,
        "leo-api.service": (
            f"[Service]\nEnvironment=PYTHONPATH={stage}/api/src:"
            "/opt/leo-v060-adaptive/a491b1ca7ee021e3e0e19a8c98becd2c9b1dae8b/src\n"
            "ExecStart=\nExecStart=/usr/bin/env PYTHONDONTWRITEBYTECODE=1 "
            f"LEO_WEB_DIST={stage}/web/dist /opt/leo-tracker/current-api/.venv/bin/leo-api\n"
        ),
    }
    receipt = {
        "revision": inventory["revision"],
        "stage": str(stage),
        "verified_files": count,
        "started_utc": datetime.now(UTC).isoformat(),
        "units": units,
        "dropins": {},
        "prior_environments": {
            unit: command("systemctl", "show", unit, "-p", "Environment", "--value")
            for unit in [*units, "leo-adaptive-analysis-queue.service"]
        },
        "capture_timer_before": command("systemctl", "is-active", "leo-v052-adaptive.timer"),
    }
    for environment in receipt["prior_environments"].values():
        assert "/opt/leo-hard60/967566245590-r1/" in environment
    for unit, content in selectors.items():
        path = Path("/etc/systemd/system") / (unit + ".d") / "zzzzzzzzzzzzzzzz-hard60-bounded.conf"
        assert not path.exists(), path
        receipt["dropins"][str(path)] = content
    (report / "activation-prepared.json").write_text(json.dumps(receipt, indent=2) + "\n")
    for path, content in receipt["dropins"].items():
        Path(path).write_text(content)
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", *units], check=True)
    except subprocess.CalledProcessError:
        for path in receipt["dropins"]:
            Path(path).unlink()
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "restart", *units], check=True)
        raise
    receipt["completed_utc"] = datetime.now(UTC).isoformat()
    receipt["capture_timer_after"] = command("systemctl", "is-active", "leo-v052-adaptive.timer")
    receipt["active"] = {unit: command("systemctl", "is-active", unit) for unit in units}
    (report / "activation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main(*sys.argv[1:])
