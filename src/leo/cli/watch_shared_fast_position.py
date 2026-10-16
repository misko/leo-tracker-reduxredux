"""Offline automatic shared-position queue alongside the unchanged legacy watcher."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from leo.application.automatic_shared_model import pending, process
from leo.storage.shared_fast_scan import SharedFastScanStore


def tick(store, pool, active, *, command, maximum_seconds, plot_command=None):
    for identifier, future in list(active.items()):
        if future.done():
            try:
                future.result()
            except Exception as error:
                print(json.dumps({"shared_job_id": identifier, "failure": str(error)}), flush=True)
            del active[identifier]
    if not active:
        job = pending(store)
        if job is not None:
            active[job["job_id"]] = pool.submit(process, job, store=store, command=command,
                                              maximum_seconds=maximum_seconds,
                                              plot_command=plot_command)


def watch(args):
    store = SharedFastScanStore(args.bulk_root, args.model_version)
    command = [args.shared_python, "-m", "leo.cli.shared_fast_position"]
    plot_command = [args.shared_python, '-m', 'leo.cli.shared_fast_orbits',
                    '--bulk-root', str(args.bulk_root), '--model-version', args.model_version]
    with store.owner("watcher") as acquired:
        if not acquired:
            raise RuntimeError("shared fast-position watcher already owned")
        with ThreadPoolExecutor(max_workers=1) as pool:
            active = {}
            while True:
                try:
                    tick(store, pool, active, command=command, maximum_seconds=args.maximum_seconds,
                         plot_command=plot_command)
                except (OSError, ValueError) as error:
                    # Discovery can race a disappearing export. Keep this independent
                    # service alive; never turn a failed identity check into a fit.
                    print(json.dumps({"shared_discovery_failure": str(error)}), flush=True)
                time.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--shared-python", required=True)
    parser.add_argument("--model-version", default="shared-scan-q-v2")
    parser.add_argument("--maximum-seconds", type=int, choices=range(1, 1201), default=1200)
    watch(parser.parse_args())
