import ast
import hashlib
import json
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification.portable_v5_transfer import simulated_document
from tools.pipeline_eval.qualification.portable_v5_trials import (
    REPORT,
    SOURCE_SNAPSHOT_ENV,
    WORKER,
    adapter_source,
    preferred_history,
)
from tools.pipeline_eval.variants import portable_v5


def test_native_port_discards_unrecognized_reference_metadata():
    doc = simulated_document(
        "anonymous",
        17_950_000_000_000_000_000,
        [{"valid_start_counter": 73, "receiver_id": 0, "candidates": []}],
        73,
    )
    doc["evaluation_reference"] = [10, 11]
    doc["source"]["receiver_geo"] = [10, 11]
    doc["provenance"]["anchor_utc_ns"] = 42
    clean = portable_v5.native_input(doc)
    assert "evaluation_reference" not in clean
    assert "receiver_geo" not in clean["source"]
    assert "anchor_utc_ns" not in clean["provenance"]
    assert clean["clock_anchor"] == doc["clock_anchor"]
    assert clean["source"]["probes"] == doc["source"]["probes"]


def test_simulated_clock_keeps_sample_bounds_and_independent_causal_bracket():
    anchor = 17_950_000_000_000_000_000
    probes = [{"valid_start_counter": 22}, {"valid_start_counter": 100_022}]
    doc = simulated_document("synthetic", anchor, probes, 22)
    before, after = (doc["clock_anchor"][k]["realtime_ns"] for k in ("before", "after"))
    assert before < anchor < after
    assert (before + after) // 2 == anchor
    assert doc["last_sample_counter"] == 3_000_000_022
    assert all(c["realtime_ns"] > after for c in doc["delivery_clocks"])
    assert len({c["realtime_ns"] - c["monotonic_ns"] for c in doc["delivery_clocks"]}) == 1


def test_archive_preserves_collection_times_and_rejects_tampered_bytes(tmp_path):
    cutoff = 100 * portable_v5.NS_HOUR
    raw = b"mock satellite text for archive-only unit test"
    digest = hashlib.sha256(raw).hexdigest()
    path = tmp_path / f"{digest}.tle"
    path.write_bytes(raw)
    stamps = [
        dict(collected_utc_ns=cutoff - portable_v5.NS_HOUR * i, sha256=digest) for i in (1, 2)
    ]
    archive = portable_v5.SnapshotArchive(stamps, cutoff, tmp_path)
    refs = archive.list_snapshots("space-track")
    assert [r.collected_utc_ns for r in refs] == [s["collected_utc_ns"] for s in stamps[::-1]]
    assert archive.read(refs[0]) == raw.decode("ascii")
    assert refs[0].digest == f"sha256:{digest}"
    assert archive.list_snapshots("other") == ()
    path.write_bytes(b"changed")
    changed = portable_v5.SnapshotArchive(stamps, cutoff, tmp_path)
    with pytest.raises(ValueError, match="sealed history"):
        changed.read(refs[0])


def test_archive_filters_aged_history_and_fails_if_future_rows_enter_worker(tmp_path):
    cutoff = 100 * portable_v5.NS_HOUR
    stamps = [
        dict(collected_utc_ns=t, sha256="2" * 64)
        for t in (cutoff + 1, cutoff - portable_v5.NS_HOUR * 73, cutoff - portable_v5.NS_HOUR)
    ]
    assert preferred_history(stamps, cutoff) == [stamps[2]]
    with pytest.raises(ValueError, match="causal"):
        portable_v5.SnapshotArchive(stamps, cutoff, tmp_path)


def test_retained_sources_match_historical_lock_and_live_import_only_changes(monkeypatch):
    snapshot = REPORT / "as-executed-source"
    monkeypatch.setenv(SOURCE_SNAPSHOT_ENV, str(snapshot))
    locked = json.loads((REPORT / "source-lock.json").read_bytes())

    def normalize(raw, *, worker):
        module = ast.parse(raw)
        scope = module
        if not worker:
            scope = next(
                node
                for node in module.body
                if isinstance(node, ast.FunctionDef) and node.name == "run"
            )
        end = 1
        while end < len(scope.body) and isinstance(scope.body[end], ast.Import | ast.ImportFrom):
            end += 1
        scope.body[1:end] = sorted(scope.body[1:end], key=ast.dump)
        return ast.dump(module)

    for path in (Path(portable_v5.__file__), WORKER):
        original = adapter_source(path).read_bytes()
        assert hashlib.sha256(original).hexdigest() == locked[path.name]
        worker = path == WORKER
        assert normalize(original, worker=worker) == normalize(path.read_bytes(), worker=worker)
