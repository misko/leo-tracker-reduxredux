from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from verified_source_audit import SourceAudit, summarize
from verified_source_audit_score import sidecar
from verified_source_text import VerifiedSourceText


def test_attribution_keeps_nested_time_disjoint_and_source_reads_separate(tmp_path):
    import hashlib

    file = tmp_path/"inputs.py"
    file.write_bytes(b"a = 2\n")
    trace = SourceAudit(tmp_path)
    with trace.bind():
        with trace.span("external", "test", "unique"):
            for _ in range(2):
                src = file.read_bytes()
                hashlib.sha256(src).hexdigest()
                code = compile(src, str(file), "exec")
                namespace = {}
                exec(code, namespace)
                assert namespace["a"] == 2
    rows = trace.events
    assert [row["repeat"] for row in rows if row["kind"] == "source_read"] == [False, True]
    assert [row["repeat"] for row in rows if row["kind"] == "source_sha256"] == [False, True]
    assert [row["repeat"] for row in rows if row["kind"] == "explicit_compile"] == [False, True]
    assert sum(row["exclusive_cpu_ns"] for row in rows) == rows[0]["cpu_ns"]
    assert sum(row["exclusive_wall_ns"] for row in rows) == rows[0]["wall_ns"]
    assert sum(row["calls"] for row in summarize(rows)["repeats"]) == 3


def test_text_cache_checks_live_loader_and_rejects_changed_metadata_even_with_old_mtime(tmp_path):
    from hashlib import sha256
    from importlib.util import module_from_spec, spec_from_file_location
    import inspect
    from unittest.mock import patch

    file = tmp_path/"released.py"
    file.write_text("def coefficient():\n    return 1\n")
    spec = spec_from_file_location("_test_reviewed_module", file)
    module = module_from_spec(spec)
    assert spec.loader is not None
    seen = []

    def original(operation):
        seen.append(operation)
        return inspect.getsource(operation)

    memo = VerifiedSourceText({file: sha256(file.read_bytes()).hexdigest()}, original)
    with patch.dict(sys.modules, {module.__name__: module}):
        spec.loader.exec_module(module)
        assert memo.source(module.coefficient) == memo.source(module.coefficient)
        assert len(seen) == 1
        old_stamp = file.stat()
        file.write_text("def coefficient():\n    return 2\n")
        os.utime(file, ns=(old_stamp.st_atime_ns, old_stamp.st_mtime_ns))
        memo.source(module.coefficient)
        assert not memo.entries and len(seen) == 2


def test_cache_does_not_share_clones_reloaded_code_or_wrappers(tmp_path):
    from functools import wraps
    from hashlib import sha256
    from importlib.util import module_from_spec, spec_from_file_location
    from types import FunctionType
    from unittest.mock import patch

    file = tmp_path/"routed.py"
    file.write_text("def phase():\n    return 1\n")
    spec = spec_from_file_location("_test_routed_module", file)
    module = module_from_spec(spec)
    counts = []

    def ordinary(operation):
        counts.append(operation)
        return str(len(counts))

    memo = VerifiedSourceText({file: sha256(file.read_bytes()).hexdigest()}, ordinary)
    with patch.dict(sys.modules, {module.__name__: module}):
        spec.loader.exec_module(module)
        loaded = module.phase
        assert memo.source(loaded) == memo.source(loaded) == "1"
        clone = FunctionType(loaded.__code__, dict(loaded.__globals__))
        assert memo.source(clone) == "2" and memo.source(clone) == "3"

        @wraps(loaded)
        def wrapper():
            return loaded()

        assert memo.source(wrapper) == "4" and memo.source(wrapper) == "5"
        loaded.__code__ = loaded.__code__.replace()
        assert memo.source(loaded) == "6"


def test_offline_verifier_rejects_changed_sidecar_document(tmp_path):
    from hashlib import sha256
    import json
    import pytest

    path = tmp_path/"position-grid.json"
    document = {"points": [1, 2]}
    data = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    envelope = dict(document=document, sha256="sha256:" + sha256(data).hexdigest())
    path.write_text(json.dumps(envelope))
    assert sidecar(path) == document
    document["points"].pop()
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="cannot verify its document"):
        sidecar(path)
