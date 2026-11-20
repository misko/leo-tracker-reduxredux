"""Run one normal collector from the explicitly selected checkout."""

import argparse
import json
import os
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns


def public_collection(shards, workers, wall_s):
    return dict(
        shards=[[list(key), chunk, visits] for key, (chunk, visits) in shards.items()],
        workers=workers,
        raw_wall_s=wall_s,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("collect",))
    parser.add_argument("root", type=Path)
    parser.add_argument("data", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("cpu", type=int)
    parser.add_argument("--payload", type=Path)
    args = parser.parse_args()

    from tools.pipeline_eval import original_receiver, whole_iq
    from tools.pipeline_eval.__main__ import encoded, write
    from tools.pipeline_eval.qualification import capture_whole, capture_whole_results
    from tools.pipeline_eval.qualification.full_v5_check import _sha

    if os.sched_getaffinity(0) != {args.cpu}:
        raise ValueError("timing process did not bind to its designated host CPU")
    expected = whole_iq.read(args.plan)
    modules = (original_receiver, capture_whole, capture_whole_results)
    for unit in modules:
        path = Path(unit.__file__).resolve()
        name = str(path.relative_to(args.root.resolve()))
        whole_iq.checked(path, expected["sources"][name])
    path = whole_iq.checked(args.data / "source-lock.json", expected["raw_source_lock_sha256"])
    lock = whole_iq.read(path)
    wall, cpu = perf_counter_ns(), process_time_ns()
    collection = original_receiver.collect(args.data, lock)
    finished = dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)
    result = dict(
        **finished,
        checkout=str(args.root),
        cpu=args.cpu,
        action=args.action,
        python_sha256=_sha(Path(os.sys.executable)),
    )
    payload = encoded(public_collection(*collection))
    result["collection_sha256"] = sha256(payload).hexdigest()
    if args.payload is not None:
        write(args.payload, payload)
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
