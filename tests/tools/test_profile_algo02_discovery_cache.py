"""The benchmark patch must preserve unrelated installed store behavior."""

import ast
from pathlib import Path

import pytest
from profile_algo02_discovery_cache import adapt

from leo.storage import fast_graph_position as current

BASE = '''from contextlib import contextmanager
class FastGraphPositionStore:
    def __init__(self, root):
        self.root = root
        self.namespace = self.root / "fast-scan-graph-position-v1" / MODEL_VERSION
    def inputs(self):
        for path in self.inputs_port.exported_tracking_inputs():
            digest = sha(path)
            yield digest
    def status(self, identifier):
        return unchanged_status(identifier)
    def verify_input(self, job):
        return full_hash_validation(job)
'''


def test_adaptation_preserves_status_and_full_validation():
    candidate = adapt(BASE, Path(current.__file__).read_text())
    trees = [ast.parse(s) for s in (BASE, candidate)]
    classes = [next(n for n in t.body if isinstance(n, ast.ClassDef)) for t in trees]
    for name in ("status", "verify_input"):
        bodies = [next(n for n in c.body if n.name == name) for c in classes]
        assert ast.dump(bodies[0]) == ast.dump(bodies[1])
    assert "self._discovery_digest(path)" in candidate
    assert "_DISCOVERY_DIGEST_LIMIT = 4096" in candidate


@pytest.mark.parametrize("source", [BASE.replace("digest = sha(path)", "digest = other(path)"),
                                     BASE + "\n# _discovery_digests\n"])
def test_rejects_unknown_or_already_modified_baseline(source):
    with pytest.raises(ValueError):
        adapt(source, Path(current.__file__).read_text())
