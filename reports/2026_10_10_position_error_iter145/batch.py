"""Serial controller; claimed incomplete jobs require explicit review."""

import json
import subprocess
import sys

from run import HERE, sha


def validate(path, label, digest):
    claim = json.loads(path.with_suffix(".claim.json").read_text())
    if claim.get("label") != label or claim.get("protocol_sha256") != digest:
        raise ValueError("Foreign claim")
    value = json.loads(path.read_text())
    if (
        value["label"] != label
        or value["protocol_sha256"] != digest
        or value["status"] not in ("complete", "failed", "attempt-failed", "model-integrity-failed")
    ):
        raise ValueError("Foreign or nonterminal receipt")


def main():
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    digest = sha(path)
    for member in plan["members"]:
        label = member["label"]
        result = HERE / "results" / (label + ".json")
        if result.exists():
            validate(result, label, digest)
            continue
        if result.with_suffix(".claim.json").exists():
            raise ValueError("Claim without terminal; no automatic retry")
        child = subprocess.run(
            [sys.executable, str(HERE / "run.py"), "--label", label], check=False
        )
        if child.returncode or not result.exists():
            raise RuntimeError("Infrastructure failure; no automatic retry")
        validate(result, label, digest)


if __name__ == "__main__":
    main()
