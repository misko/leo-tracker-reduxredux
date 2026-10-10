"""Remove only this rollout's adaptive worker and queue selectors."""

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from activate import BASE, HERE, QUEUE_TIMER, QUEUE_UNIT, STAGE, effective_path


def main():
    if os.geteuid() != 0:
        raise PermissionError("rollback requires root")
    activation = json.loads((HERE / "activation.json").read_text())
    if activation["stage"] != str(STAGE) or (HERE / "rollback.json").exists():
        raise ValueError("unexpected or already rolled-back activation")
    paths = [Path(value) for value in activation["dropins"]]
    for path in paths:
        if path.read_text() != f"[Service]\nEnvironment=PYTHONPATH={STAGE}/worker/src\n":
            raise ValueError(f"selector changed after activation: {path}")
    timer_active = (
        subprocess.run(
            ["systemctl", "is-active", QUEUE_TIMER], capture_output=True, text=True
        ).stdout.strip()
        == "active"
    )
    if timer_active:
        subprocess.run(["systemctl", "stop", QUEUE_TIMER], check=True)
    subprocess.run(["systemctl", "stop", QUEUE_UNIT], check=True)
    for path in paths:
        path.unlink()
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "--no-block", *activation["workers"]], check=True)
    if timer_active:
        subprocess.run(["systemctl", "start", QUEUE_TIMER], check=True)
    if effective_path(QUEUE_UNIT) != str(BASE):
        raise ValueError("queue selector did not revert to inherited B7")
    receipt = dict(
        rolled_back_utc=datetime.now(UTC).isoformat(),
        stage=str(STAGE),
        restored_selector=str(BASE),
        workers=activation["workers"],
        queue_timer_was_active=timer_active,
    )
    (HERE / "rollback.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
