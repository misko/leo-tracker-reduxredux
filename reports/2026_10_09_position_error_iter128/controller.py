"""Serial bounded launcher. Parent assigns at most two global worker slots."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from run import digest, write_new

HERE = Path(__file__).resolve().parent


def launch(labels, plan, protocol_digest, *, here=HERE, call=subprocess.run):
    allowed = {m["label"] for m in plan["members"]}
    if len(labels) != len(set(labels)) or not set(labels) <= allowed:
        raise ValueError("invalid or duplicate member selection")
    for label in labels:
        result = here / "results" / label / "result.json"
        if result.exists():
            terminal = json.loads(result.read_text())
            if terminal["protocol_sha256"] != protocol_digest or terminal["label"] != label:
                raise ValueError("stale terminal receipt")
            if terminal["status"] not in ("complete", "complete-with-failures"):
                raise ValueError("unknown terminal status")
            continue
        claim = here / "controller-claims" / f"{label}.json"
        write_new(claim, {"label": label, "protocol_sha256": protocol_digest})
        child = call([sys.executable, str(here / "run.py"), "--label", label], check=False)
        write_new(
            claim.with_suffix(".exit.json"),
            {"label": label, "protocol_sha256": protocol_digest, "returncode": child.returncode},
        )
        if child.returncode != 0 or not result.exists():
            raise RuntimeError(f"{label}: child failure/missing terminal; no automatic retry")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", nargs="+", required=True)
    args = parser.parse_args()
    path = HERE / "protocol.json"
    launch(args.labels, json.loads(path.read_text()), digest(path))


if __name__ == "__main__":
    main()
