"""Research-only, operation-local reuse over public terminal/verify_input ports.

No installed worker or store implementation is patched. This tests validation
overhead only, not numerical inference or end-to-end ALGO07* qualification.
"""
import argparse
import copy
import hashlib
import importlib
import json
import time
from pathlib import Path

from leo.cli.algo07_profile import digest, write_new


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


class TerminalReuse:
    """A narrow research port; create a new instance for each outer read operation."""

    def __init__(self, source):
        self.source = source
        self.entries = {}
        self.hits = 0
        self.misses = 0

    def terminal(self, job):
        key = canonical(job)
        previous = self.entries.get(key)
        if previous is not None:
            value, receipt = previous
            # This is deliberately not a stat/mtime cache. Revalidate the entire
            # input chain, including native bytes and acquisition provenance.
            self.source.verify_input(job)
            path = Path(receipt['path'])
            if (path.resolve(strict=True) == path
                    and 'sha256:' + digest(path) == receipt['sha256']):
                self.hits += 1
                return copy.deepcopy(previous)
            del self.entries[key]
        self.misses += 1
        value, receipt = self.source.terminal(job)
        # Bind the returned object to the exact public bytes before remembering
        # it; reject a mutation during the underlying read rather than cache it.
        payload = Path(receipt['path']).read_bytes()
        if ('sha256:' + hashlib.sha256(payload).hexdigest() != receipt['sha256']
                or canonical(json.loads(payload)) != canonical(value)):
            raise ValueError('Public terminal changed during reuse preparation')
        self.entries[key] = copy.deepcopy((value, receipt))
        return copy.deepcopy(self.entries[key])


def chain(root):
    """Compose unchanged storage adapters through their explicit source ports."""
    from leo.storage.fast_graph_position import FastGraphPositionStore

    source = FastGraphPositionStore(root)
    ports = []
    for version in range(2, 7):
        port = TerminalReuse(source)
        ports.append(port)
        module = importlib.import_module(f'leo.storage.fast_graph_position_v{version}')
        cls = getattr(module, f'FastGraphPositionStoreV{version}')
        source = cls(root, **{'baseline' if version == 2 else 'incumbent': port})
    return source, ports


def run(args):
    from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6

    if args.mode == 'reuse':
        store, ports = chain(args.root)
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
