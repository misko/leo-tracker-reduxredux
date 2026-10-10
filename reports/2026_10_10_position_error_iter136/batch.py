"""Serial twelve-member audit, preserving terminal failures and crash claims."""

import json
import subprocess
import sys

from run import HERE, sha


def terminal(path, label, digest):
    result = json.loads(path.read_text())
    if (
        result["label"] != label
        or result["protocol_sha256"] != digest
        or result["status"] not in ("complete", "failed")
    ):
        raise ValueError("foreign or nonterminal receipt")


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = sha(protocol)
    labels = [m["label"] for m in plan["members"]]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError("fixed twelve required")
    for label in labels:
        path = HERE / "results" / (label + ".json")
        if path.exists():
            terminal(path, label, digest)
            continue
        if path.with_suffix(".claim.json").exists():
            raise ValueError("claimed member without terminal; explicit review required")
        child = subprocess.run(
            [sys.executable, str(HERE / "run.py"), "--label", label], check=False
        )
        if child.returncode != 0 or not path.exists():
            raise RuntimeError("member failed; no automatic retry: " + label)
        terminal(path, label, digest)


if __name__ == "__main__":
    main()
