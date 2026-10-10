"""Serial fixed12 launcher; claimed crashes are never silently retried."""

import json
import subprocess
import sys

from run import HERE, sha


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = sha(protocol)
    output = HERE / "results"
    output.mkdir(exist_ok=True)
    for member in plan["members"]:
        label = member["label"]
        path = output / (label + ".json")
        if path.exists():
            result = json.loads(path.read_text())
            if result["label"] != label or result["protocol_sha256"] != digest:
                raise ValueError("foreign terminal receipt")
            if result["status"] not in (
                "complete",
                "failed",
                "attempt-failed",
                "model-integrity-failed",
            ):
                raise ValueError("unknown terminal status")
            continue
        if path.with_suffix(".claim.json").exists():
            raise ValueError("claimed member without terminal; explicit review required")
        child = subprocess.run(
            [sys.executable, str(HERE / "run.py"), "--label", label], check=False
        )
        if child.returncode != 0 or not path.exists():
            raise RuntimeError("member process failed; no automatic retry: " + label)


if __name__ == "__main__":
    main()
