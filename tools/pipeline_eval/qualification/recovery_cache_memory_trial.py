"""Exercise exact scratch-cache lifetime control on ordinary DS29-0082."""

import argparse
import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import v5_composed_memory
from ..variants import v5_recovery_cache_memory as cache
from . import composed_memory_trial as apparatus
from . import discovery_memory_trial as discovery
from . import nomination_memory_trial as prior
from . import working_memory_trial
from .full_v5_check import _sha

REPORT = prior.REPORT.with_name("recovery-cache-memory")
RUNS = prior.RUNS.with_name("recovery-cache-memory")
WORKER = Path(__file__).with_name("recovery_cache_memory_worker.py")


def source():
    earlier = prior.REPORT / "source-lock.json"
    if prior.source() != json.loads(earlier.read_bytes()):
        raise ValueError("the tiled nomination control differs from the original lock")
    paths = (Path(__file__), WORKER, Path(cache.__file__), REPORT / "PROTOCOL.md")
    return dict(
        source={p.name: _sha(p) for p in paths},
        nomination_source_sha256=_sha(earlier),
        nomination_prediction_sha256=_sha(prior.REPORT / "prediction-lock.json"),
        case=apparatus.CASE,
        cpu=apparatus.CPU,
        nice=discovery.NICE,
        write_window_bytes=cache.WRITE_WINDOW_BYTES,
        memory_max_bytes=apparatus.MEMORY,
    )


def reference():
    lock = json.loads((prior.REPORT / "prediction-lock.json").read_bytes())
    path = prior.REPORT / "uncapped-positions.jsonl.gz"
    if lock["cases"] != [apparatus.CASE] or _sha(path) != lock["files"][path.name]:
        raise ValueError("the tiled nomination prediction archive differs from its lock")
    return json.loads(gzip.decompress(path.read_bytes()))


def same_science(stock, candidate):
    check = discovery.same_science(stock, candidate)
    if check.get("exact"):
        proof = prior.nomination_parity(stock, candidate)
        check["equal"].update(proof["checks"])
        check["exact"] = all(check["equal"].values())
    return check


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "replay", "cap", "publish"))
    for name, default in (("report", REPORT), ("runs", RUNS), ("raw", working_memory_trial.RAW)):
        p.add_argument("--" + name, type=local_output, default=default)
    args = p.parse_args()
    if args.action == "seal":
        path, candidate = args.report / "source-lock.json", source()
        if path.exists() and json.loads(path.read_bytes()) != candidate:
            raise ValueError("refuse to replace a previous source seal")
        if not path.exists():
            save_json(path, candidate)
        return
    with (
        patch.multiple(
            apparatus, WORKER=WORKER, seal=source, reference=reference, same_science=same_science
        ),
        patch.multiple(v5_composed_memory, METHOD=cache.METHOD, BOUNDARY=cache.BOUNDARY),
    ):
        if args.action == "replay":
            if os.getpriority(os.PRIO_PROCESS, 0) != discovery.NICE:
                raise ValueError(f"start the unrestricted worker with nice -n {discovery.NICE}")
            apparatus.replay(args.runs, args.report, args.raw)
        elif args.action == "cap":
            discovery.cap(args.runs, args.report)
        else:
            apparatus.publish(args.runs, args.report)


if __name__ == "__main__":
    main()
