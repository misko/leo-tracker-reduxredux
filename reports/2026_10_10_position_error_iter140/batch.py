"""Serial frozen-membership controller; no retries or implicit worker pool."""

import argparse
import json
import subprocess
import sys

from run import HERE, sha


def run_members(plan, digest, here, invoke, maximum=None):
    def terminal(output, label):
        if not output.exists():
            raise ValueError("Child exited without terminal receipt; no implicit retry")
        result = json.loads(output.read_text())
        if (
            result["label"] != label
            or result["protocol_sha256"] != digest
            or result["status"]
            not in ("complete", "failed", "attempt-failed", "model-integrity-failed")
        ):
            raise ValueError("Foreign/nonterminal result")

    count = 0
    for binding in plan["members"]:
        output = here / "results" / (binding["label"] + ".json")
        if output.exists():
            terminal(output, binding["label"])
            continue
        if output.with_suffix(".claim.json").exists():
            raise ValueError(
                "Claim exists without terminal receipt; inspect interrupted worker, no retry"
            )
        invoke(binding["label"])
        terminal(output, binding["label"])
        count += 1
        if maximum is not None and count >= maximum:
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-members", type=int)
    args = parser.parse_args()
    if args.max_members is not None and args.max_members < 1:
        raise ValueError("Positive member cap required")
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())

    def invoke(label):
        subprocess.run([sys.executable, str(HERE / "run.py"), "--label", label], check=True)

    run_members(plan, sha(protocol), HERE, invoke, args.max_members)


if __name__ == "__main__":
    main()
