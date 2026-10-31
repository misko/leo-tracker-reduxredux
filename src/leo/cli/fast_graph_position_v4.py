"""Watch only new completed ALGO04 jobs; bounded single-worker ALGO05 canary."""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from leo.application.automatic_fast_graph_v4 import process
from leo.storage.fast_graph_position_v4 import FastGraphPositionStoreV4


def watch(args):
    store = FastGraphPositionStoreV4(args.bulk_root)
    worker = Path(__file__).resolve().parents[3] / "tools/algo05_production_worker.py"
    command = [sys.executable, "-B", str(worker), "--bulk-root", str(args.bulk_root)]
    with store.owner("watcher") as acquired:
        if not acquired:
            raise RuntimeError("ALGO05 watcher is already owned")
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = None
            while True:
                if active is not None and active.done():
                    try:
                        result = active.result()
                        if result is not None:
                            print(
                                json.dumps(dict(job_id=result["job_id"], state=result["state"])),
                                flush=True,
                            )
                    except Exception as error:
                        print(json.dumps(dict(failure=str(error))), flush=True)
                    active = None
                if active is None:
                    try:
                        for job in store.inputs(
                            minimum_completed_utc_ns=args.minimum_completed_utc_ns
                        ):
                            if args.source_job and job["source_job"]["job_id"] != args.source_job:
                                continue
                            status = store.status(job["job_id"])
                            if status is None or status["state"] == "running":
                                active = pool.submit(
                                    process,
                                    job,
                                    store=store,
                                    command=command,
                                    maximum_seconds=args.maximum_seconds,
                                )
                                break
                    except (OSError, ValueError, KeyError) as error:
                        print(json.dumps(dict(discovery_failure=str(error))), flush=True)
                if args.once:
                    if active is not None:
                        print(json.dumps(active.result()), flush=True)
                    return
                time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--minimum-completed-utc-ns", type=int, required=True)
    parser.add_argument("--maximum-seconds", type=int, choices=range(1, 1201), default=1200)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--source-job", help="Explicit completed ALGO04 canary job; requires --once"
    )
    args = parser.parse_args()
    if args.minimum_completed_utc_ns <= 0 or (args.source_job and not args.once):
        parser.error("Positive deployment cutoff required; --source-job requires --once")
    watch(args)


if __name__ == "__main__":
    main()

