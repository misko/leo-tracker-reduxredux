"""Apply the outcome-length repair to workers; numerical policy and API stay fixed."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import activate

HERE = Path(__file__).resolve().parent
STAGE = Path("/opt/leo-b7/88e231eb1-r1")

if __name__ == "__main__":
    activate.STAGE = STAGE
    revision, count = activate.verify_stage()
    initial = json.loads((HERE / "activation.json").read_text())
    replacements = {}
    for name, expected in initial["dropins"].items():
        if "leo-api.service.d" in name:
            continue
        path = Path(name)
        assert path.read_text() == expected
        replacements[name] = expected.replace(initial["stage"], str(STAGE))
    receipt = dict(
        revision=revision,
        verified_files=count,
        stage=str(STAGE),
        started_utc=datetime.now(UTC).isoformat(),
        dropins=replacements,
        reason="Queue terminal outcome shortened to fit VARCHAR(32)",
        numerical_configuration_unchanged=True,
        api_stage=initial["stage"],
    )
    (HERE / "queue-repair-prepared.json").write_text(json.dumps(receipt, indent=2) + "\n")
    for name, value in replacements.items():
        Path(name).write_text(value)
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    units = [u for u in initial["units"] if u != "leo-api.service"]
    subprocess.run(["systemctl", "restart", "--no-block", *units], check=True)
    (HERE / "queue-repair.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(dict(revision=revision, worker_units=len(units))))
