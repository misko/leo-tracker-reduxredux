"""Atomically select the qualified B7 overlay for future fast-scan adapters.

The fast-analysis daemon launches this wrapper for each standard analysis.
Replacing the wrapper leaves an already running child on its original source.
"""

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
WRAPPER = Path("/opt/leo-fast-auto/20261010-r1/bin/standard-python")
OLD_SOURCE = "/opt/leo-b7/88e231eb1-r1/worker/src"
NEW_SOURCE = "/opt/leo-b7/a620e14f3-retained-r1/worker/src"
PYTHON = "/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python"
CONFIG_DIGEST = "sha256:d7726729fd10b9a04e818dee0e1273a5cc3e8ee800fb247c44fee52470ed01fe"
OLD = f'#!/bin/sh\nexport PYTHONPATH={OLD_SOURCE}\nexec {PYTHON} "$@"\n'.encode()
NEW = f'#!/bin/sh\nexport PYTHONPATH={NEW_SOURCE}\nexec {PYTHON} "$@"\n'.encode()


def sha256(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def replace_atomically(content):
    fd, name = tempfile.mkstemp(prefix=".standard-python-retained-", dir=WRAPPER.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o755)
        os.chown(name, 0, 0)
        os.replace(name, WRAPPER)
        directory = os.open(WRAPPER.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def validate():
    source = (
        "from leo.cli.regional_position import configuration; "
        "from leo.contracts.digests import canonical_digest; "
        "import leo.cli.regional_position as module; "
        "print(canonical_digest(configuration())); print(module.__file__)"
    )
    completed = subprocess.run(
        [
            "runuser", "-u", "leo", "--", "env", "PYTHONDONTWRITEBYTECODE=1",
            str(WRAPPER), "-c", source,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    digest, module = completed.stdout.strip().splitlines()
    if digest != CONFIG_DIGEST or not module.startswith(NEW_SOURCE + "/"):
        raise ValueError("fast adapter did not import the new B7 overlay")
    return {"configuration_sha256": digest, "module": module}


def main():
    if os.geteuid() != 0 or (HERE / "fast-adapter-activation.json").exists():
        raise PermissionError("root and a fresh activation receipt are required")
    if WRAPPER.read_bytes() != OLD:
        raise ValueError("fast adapter wrapper changed unexpectedly")
    if not (HERE / "parity.json").exists() or not (HERE / "activation.json").exists():
        raise ValueError("adaptive rollout parity and activation are required")
    replace_atomically(NEW)
    try:
        validation = validate()
    except Exception:
        replace_atomically(OLD)
        raise
    receipt = {
        "status": "active",
        "activated_utc": datetime.now(UTC).isoformat(),
        "wrapper": str(WRAPPER),
        "previous_sha256": sha256(OLD),
        "active_sha256": sha256(NEW),
        "previous_source": OLD_SOURCE,
        "active_source": NEW_SOURCE,
        "current_child_uninterrupted": True,
        "validation": validation,
    }
    (HERE / "fast-adapter-activation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], **validation}))


if __name__ == "__main__":
    main()
