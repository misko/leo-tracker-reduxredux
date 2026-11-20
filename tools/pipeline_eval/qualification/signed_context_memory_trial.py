"""Test the signed consumer's sampled widths against the exact two-change receiver."""

import argparse
import gzip
import json
import os
from pathlib import Path
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import v5_composed_memory, v5_lean
from ..variants import v5_signed_context_memory as signed
from . import compact_memory_combined_trial as previous
from . import composed_memory_trial as apparatus
from . import discovery_memory_trial as discovery
from . import working_memory_trial
from .full_v5_check import _sha

REPORT = previous.REPORT.with_name("signed-context-memory")
RUNS = previous.RUNS.with_name("signed-context-memory")
WORKER = Path(__file__).with_name("signed_context_memory_worker.py")


def source():
    earlier = previous.source()
    path = previous.REPORT / "source-lock.json"
    if json.loads(path.read_bytes()) != earlier:
        raise ValueError("the two-change receiver differs from the original lock")
    consumer = v5_lean.SOURCE / "leo/analysis/localization_v3/signed_context.py"
    paths = (Path(__file__), Path(signed.__file__), WORKER, consumer, REPORT / "PROTOCOL.md")
    return dict(
        source={p.name: _sha(p) for p in paths},
        previous_source_sha256=_sha(path),
        previous_prediction_sha256=_sha(previous.REPORT / "prediction-lock.json"),
        case=apparatus.CASE,
        cpu=apparatus.CPU,
        nice=discovery.NICE,
        memory_max_bytes=apparatus.MEMORY,
    )


def reference():
    lock = json.loads((previous.REPORT / "prediction-lock.json").read_bytes())
    path = previous.REPORT / "uncapped-positions.jsonl.gz"
    if lock["cases"] != [apparatus.CASE] or _sha(path) != lock["files"][path.name]:
        raise ValueError("the previous two-change prediction archive differs from its lock")
    return json.loads(gzip.decompress(path.read_bytes()))


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
            apparatus,
            WORKER=WORKER,
            seal=source,
            reference=reference,
            same_science=discovery.same_science,
        ),
        patch.multiple(v5_composed_memory, METHOD=signed.METHOD, BOUNDARY=signed.BOUNDARY),
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
