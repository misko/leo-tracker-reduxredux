"""Serial per-member controller; the engine owns immutable six-slice accounting."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TERMINAL = {"complete", "budget-exhausted", "failed", "input-failed"}


def run_member(label, *, here=HERE, invoke=subprocess.run):
    """Run baseline then candidate, stopping on errors or lack of checkpoint progress.

    One process runs one numerical child at a time. The parent may launch at most
    two controllers. Six claimed slices plus one budget-finalization invocation
    are allowed per phase; only the engine can claim or spend a numerical slice.
    Existing started receipts count, including interrupted or failed invocations.
    """
    if not label or Path(label).name != label or label in {".", ".."}:
        raise ValueError("Expected one membership label, not a path")
    directory = here / "results" / label
    protocol_digest = hashlib.sha256((here / "protocol.json").read_bytes()).hexdigest()

    def terminal_status(marker):
        outcome = json.loads(marker.read_text())
        if outcome.get("protocol_sha256") != protocol_digest:
            raise ValueError("Phase result belongs to a different frozen protocol")
        if outcome.get("status") not in TERMINAL:
            raise ValueError("Phase result has an unknown terminal status")
        return outcome["status"]

    outcomes = {}
    for phase in ("baseline", "candidate"):
        marker = directory / f"{phase}.json"
        for _ in range(7):
            if marker.exists():
                outcomes[phase] = terminal_status(marker)
                break
            claims = directory / "slices"
            before = set(claims.glob(f"{phase}-*.started.json"))
            completed = invoke(
                [sys.executable, str(here / "run.py"), "--label", label, "--phase", phase],
                cwd=ROOT,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"{phase} driver exited {completed.returncode}; receipts retained"
                )
            after = set(claims.glob(f"{phase}-*.started.json"))
            if len(after) > 6:
                raise RuntimeError("Engine exceeded its six-slice claim budget")
            if not marker.exists() and not after > before:
                raise RuntimeError("No new slice or terminal receipt; refusing an idle retry loop")
            if marker.exists():
                outcomes[phase] = terminal_status(marker)
                break
        else:
            raise RuntimeError("Phase did not finalize within six slices and finalization call")
        if outcomes[phase] != "complete":
            return outcomes
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(name) != "1":
            raise ValueError(f"{name}=1 is required")
    print(json.dumps(run_member(args.label)), flush=True)


if __name__ == "__main__":
    main()
