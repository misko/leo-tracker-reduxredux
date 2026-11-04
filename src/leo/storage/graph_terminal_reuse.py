"""Opt-in terminal reads with operation-local, byte-verified ancestor reuse.

Normal production stores do not import this adapter. Each terminal() call creates
a fresh chain; entries never survive an outer read, export or worker invocation.
"""
import copy
import hashlib
import importlib
import json
from pathlib import Path

from leo.storage.fast_graph_position import FastGraphPositionStore, sha
from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()


class TerminalReuse:
    """Narrow ancestor port, owned by one terminal-read operation."""

    def __init__(self, source):
        self.source = source
        self.entries = {}
        self.hits = 0
        self.misses = 0

    def terminal(self, job):
        key = canonical(job)
        previous = self.entries.get(key)
        if previous is not None:
            _, receipt = previous
            # Revalidate native bytes, acquisition provenance and the complete
            # source chain; do not trust mtime or a previous input verification.
            self.source.verify_input(job)
            path = Path(receipt['path'])
            if path.resolve(strict=True) == path and sha(path) == receipt['sha256']:
                self.hits += 1
                return copy.deepcopy(previous)
            del self.entries[key]
        self.misses += 1
        value, receipt = self.source.terminal(job)
        payload = Path(receipt['path']).read_bytes()
        if ('sha256:' + hashlib.sha256(payload).hexdigest() != receipt['sha256']
                or canonical(json.loads(payload)) != canonical(value)):
            raise ValueError('Public terminal changed during reuse preparation')
        self.entries[key] = copy.deepcopy((value, receipt))
        return copy.deepcopy(self.entries[key])


def terminal_read_chain(root):
    """Build a fresh six-stage read chain and its operation-local diagnostic ports."""
    source = FastGraphPositionStore(root)
    ports = []
    for version in range(2, 7):
        port = TerminalReuse(source)
        ports.append(port)
        module = importlib.import_module(f'leo.storage.fast_graph_position_v{version}')
        cls = getattr(module, f'FastGraphPositionStoreV{version}')
        source = cls(root, **{'baseline' if version == 2 else 'incumbent': port})
    return source, ports


class GraphTerminalReader:
    """Opt-in read port with a fresh validation scope on every public call."""

    def __init__(self, root):
        self.root = Path(root).resolve()

    def terminal(self, job):
        store, _ = terminal_read_chain(self.root)
        return store.terminal(job)


class FastGraphPositionStoreV6ReadReuse(FastGraphPositionStoreV6):
    """Experimental final-stage adapter; other job lifecycle methods are unchanged."""

    def __init__(self, root):
        super().__init__(root)

    def terminal(self, job):
        return GraphTerminalReader(self.root).terminal(job)
