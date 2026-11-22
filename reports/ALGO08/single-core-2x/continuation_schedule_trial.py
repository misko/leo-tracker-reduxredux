"""Check the prior and future timestamp support of saved ALGO08 receiver lanes."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from tools.pipeline_eval.variants.experimental.continuation_schedule import inspect


def audit(name, path):
    data = path.read_bytes()
    probes = json.loads(data)["source"]["probes"]
    start = process_time()
    needed, publishable = inspect(probes)
    cpu = process_time() - start
    selected = {i for i, p in enumerate(probes) if p["candidates"]}
    if not selected <= publishable:
        raise ValueError("A measured continuation exceeds the schedule envelope")
    return dict(name=name, native_sha256=sha256(data).hexdigest(), lanes=len(probes),
                selected=len(selected), potentially_publishable=len(publishable),
                safely_skippable=len(probes)-len(needed), schedule_cpu_s=cpu)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", nargs=2, action="append", required=True, metavar=("NAME", "DETECTIONS"))
    args = parser.parse_args()
    print(json.dumps([audit(name, Path(path)) for name, path in args.case], indent=2))
