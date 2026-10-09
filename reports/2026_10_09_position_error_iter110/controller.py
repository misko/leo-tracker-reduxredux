"""Bounded two-shard pilot launcher; every launch has an exclusive immutable claim."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def authority(here):
    path = here / "protocol.json"
    plan = json.loads(path.read_text())
    members = plan["members"]
    labels = [b["member"]["inventory_label"] for b in members]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError("Exactly twelve distinct frozen members required")
    if any(Path(label).name != label or label in (".", "..") for label in labels):
        raise ValueError("Unsafe inventory label")
    return members, hashlib.sha256(path.read_bytes()).hexdigest()


def terminal(here, binding, digest):
    member = binding["member"]
    path = here / "results" / f"{member['inventory_label']}.json"
    if not path.exists():
        return None
    row = json.loads(path.read_text())
    if row.get("protocol_sha256") != digest or row.get("member") != member:
        raise ValueError("Terminal receipt does not match frozen member/protocol")
    if row.get("status") not in ("complete", "failed", "input-failed"):
        raise ValueError("Unknown terminal status")
    return dict(member=member, status=row["status"], error=row.get("error"))


def coverage(here, members, digest):
    result = []
    for binding in members:
        row = terminal(here, binding, digest)
        if row is None:
            label = binding["member"]["inventory_label"]
            claim = here / "controller-claims" / f"{label}.json"
            if claim.exists():
                stored = json.loads(claim.read_text())
                if stored["protocol_sha256"] != digest or stored["member"] != binding["member"]:
                    raise ValueError("Claim does not match frozen member/protocol")
            row = dict(
                member=binding["member"],
                status="claimed-without-terminal" if claim.exists() else "unlaunched",
            )
        result.append(row)
    return result


def launch(shard, maximum_members=6, *, here=HERE, invoke=subprocess.run):
    here = Path(here)
    if shard not in (0, 1) or not 1 <= maximum_members <= 6:
        raise ValueError("Use shard0/1 and maximum-members in1..6")
    members, digest = authority(here)
    launched = 0
    for ordinal, binding in enumerate(members):
        if ordinal % 2 != shard:
            continue
        if terminal(here, binding, digest) is not None:
            continue
        if launched == maximum_members:
            break
        member = binding["member"]
        label = member["inventory_label"]
        claim = here / "controller-claims" / f"{label}.json"
        # Exclusive creation intentionally fails after a claimed crash. No inferred retry.
        write(claim, dict(member=member, shard=shard, protocol_sha256=digest))
        try:
            child = invoke(
                [sys.executable, str(here / "engine.py"), "--label", label], cwd=ROOT, check=False
            )
        except Exception as error:
            write(
                claim.with_suffix(".exit.json"),
                dict(
                    protocol_sha256=digest, member=member, status="launch-error", error=repr(error)
                ),
            )
            raise
        launched += 1
        write(
            claim.with_suffix(".exit.json"),
            dict(
                protocol_sha256=digest, member=member, status="exited", returncode=child.returncode
            ),
        )
        if child.returncode:
            raise RuntimeError(f"{label}: child exited{child.returncode}; no automatic retry")
        if terminal(here, binding, digest) is None:
            raise RuntimeError(f"{label}: missing terminal; claim preserved, no automatic retry")
    return dict(
        shard=shard,
        launched=launched,
        protocol_sha256=digest,
        coverage=coverage(here, members, digest),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--maximum-members", type=int, default=6)
    args = parser.parse_args()
    for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(variable) != "1":
            raise ValueError(f"{variable}=1 required")
    print(json.dumps(launch(args.shard, args.maximum_members), indent=2))
