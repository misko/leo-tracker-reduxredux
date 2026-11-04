"""Research-only, operation-local reuse over public terminal/verify_input ports.

No installed worker or store implementation is patched. This tests validation
overhead only, not numerical inference or end-to-end ALGO07* qualification.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

from leo.cli.algo07_profile import digest, write_new
from leo.storage import graph_terminal_reuse
from leo.storage.graph_terminal_reuse import canonical, terminal_read_chain


def run(args):
    from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6

    if args.mode == 'reuse':
        store, ports = terminal_read_chain(args.root)
    else:
        store, ports = FastGraphPositionStoreV6(args.root), []
    job = store.status(args.job)
    if not job or job['state'] != 'complete':
        raise ValueError('Completed public job required')
    began = time.perf_counter()
    value, receipt = store.terminal(job)
    elapsed = time.perf_counter() - began
    result = dict(kind='algo07-terminal-reuse-probe', mode=args.mode, root=str(args.root.resolve()),
                  job_id=args.job, wall_seconds=elapsed, terminal_receipt=receipt,
                  full_return_sha256=hashlib.sha256(canonical((value, receipt))).hexdigest(),
                  probe_sha256=digest(Path(__file__)),
                  adapter_sha256=digest(Path(graph_terminal_reuse.__file__)),
                  reuse=[dict(algorithm=f'ALGO{i:02d}', hits=p.hits, misses=p.misses)
                         for i, p in enumerate(ports, 2)],
                  scientific_inference_rerun=False, full_ds26_verified=False,
                  production_modified=False)
    write_new(args.output, result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--mode', choices=('baseline', 'reuse'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args())
