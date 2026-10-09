"""Restore previous worker/queue selectors, retaining V3 readers by default."""

import argparse
import json
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-api",
        action="store_true",
        help="Also restore the previous API if its new reader is faulty",
    )
    args = parser.parse_args()
    assert os.geteuid() == 0
    receipt = json.loads((HERE / "activation-prepared.json").read_text())
    repair = HERE / "queue-repair.json"
    if repair.exists():
        receipt["dropins"].update(json.loads(repair.read_text())["dropins"])
    for name, content in receipt["dropins"].items():
        path = Path(name)
        if "leo-api.service.d" in name and not args.include_api:
            continue
        assert path.is_relative_to("/etc/systemd/system") and path.name.endswith("-hard60-b7.conf")
        if path.exists():
            assert path.read_text() == content, "Concurrent selector change; preserve it"
            path.unlink()
    units = [u for u in receipt["units"] if args.include_api or u != "leo-api.service"]
    subprocess.run(["systemctl", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "restart", "--no-block", *units], check=True)
    print(
        json.dumps(
            dict(
                restored_units=units,
                api_reader_retained=not args.include_api,
                artifacts_and_checkpoints_preserved=True,
            )
        )
    )
