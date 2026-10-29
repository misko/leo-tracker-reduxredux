"""Watch existing fast GLRT exports with the causal graph-position release."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import time

from leo.application.automatic_fast_graph import process
from leo.storage.fast_graph_position import FastGraphPositionStore


def watch(args):
    store = FastGraphPositionStore(args.bulk_root)
    worker = Path(__file__).resolve().parents[3] / "tools/fast_graph_worker.py"
    command = [sys.executable, "-B", str(worker), "--tle-root", str(args.tle_root)]
    with store.owner("watcher") as acquired:
        if not acquired:
            raise RuntimeError("Graph-position watcher is already owned")
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = None
            while True:
                if active is not None and active.done():
                    try:
                        result = active.result()
                        print(json.dumps(dict(job_id=result["job_id"], state=result["state"])), flush=True)
                    except Exception as error:
                        print(json.dumps(dict(failure=str(error))), flush=True)
                    active = None
                if active is None:
                    try:
                        for job in store.inputs():
                            status = store.status(job["job_id"])
                            if status is None or status["state"] == "running":
                                active = pool.submit(process, job, store=store, command=command,
                                                     maximum_seconds=args.maximum_seconds)
                                break
                    except (OSError, ValueError) as error:
                        print(json.dumps(dict(discovery_failure=str(error))), flush=True)
                if args.once:
                    if active is not None:
                        print(json.dumps(active.result()), flush=True)
                    return
                time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    parser.add_argument("--maximum-seconds", type=int, choices=range(1, 1201), default=1200)
    parser.add_argument("--once", action="store_true")
    watch(parser.parse_args())


if __name__ == "__main__":
    main()
