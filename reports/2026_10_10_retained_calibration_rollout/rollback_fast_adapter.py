"""Restore the exact previous fast-scan adapter wrapper after an incident."""

import json
import os

from activate_fast_adapter import HERE, NEW, OLD, WRAPPER, replace_atomically, sha256


def main():
    if os.geteuid() != 0:
        raise PermissionError("root is required")
    receipt = json.loads((HERE / "fast-adapter-activation.json").read_text())
    if (
        receipt["wrapper"] != str(WRAPPER)
        or receipt["active_sha256"] != sha256(NEW)
        or receipt["previous_sha256"] != sha256(OLD)
        or WRAPPER.read_bytes() != NEW
    ):
        raise ValueError("fast adapter state changed since activation")
    replace_atomically(OLD)
    print(json.dumps({"status": "restored", "wrapper": str(WRAPPER)}))


if __name__ == "__main__":
    main()
