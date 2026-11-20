import json
from pathlib import Path

import pytest

from tools.pipeline_eval import original_receiver as receiver


def test_pruned_cli_composes_with_row_wise_and_interior_guard(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setattr(receiver, "input_case", lambda *args: {"id": "fixture"})

    def prepare(*args, **options):
        assert options == dict(peak_selector="row-wise", interior_guard=True, fine_backend="pruned")
        out.mkdir()
        return options

    def run(path, plan):
        assert path == out and plan["fine_backend"] == "pruned"
        return dict(id="fixture", status="stage_only", stage="raw")

    monkeypatch.setattr(receiver, "prepare", prepare)
    monkeypatch.setattr(receiver, "run", run)
    assert (
        receiver.main(
            [
                "--case",
                "fixture",
                "--out",
                str(out),
                "--cpus",
                "3",
                "--smoke",
                "--peak-selector",
                "row-wise",
                "--interior-guard",
                "--fine-search",
                "pruned",
            ]
        )
        == 0
    )
    assert json.loads((out / "summary.json").read_bytes())["setup_wall_s"] >= 0


def test_fine_binary_build_reuse_and_digest_gate(tmp_path, monkeypatch):
    binary = b"qualified fixture bytes"
    shelf = tmp_path / "kernel-shelf"
    shelf.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    library = shelf / "fine_search.so"
    library.write_bytes(binary)
    monkeypatch.setattr(receiver, "FINE_LIBRARY_SHA", receiver._sha(library))
    calls = []

    def build(directory):
        calls.append(directory)
        target = directory / "fine_search.so"
        target.write_bytes(binary)
        return target, ["qualified compiler"]

    monkeypatch.setattr(receiver.fine_search, "build", build)
    preinstalled, use = receiver.pruned_library(out, shelf)
    assert preinstalled == library and use["mode"] == "reused" and use["command"] is None
    library.write_bytes(b"bad replacement")
    with pytest.raises(ValueError, match="declared SHA-256"):
        receiver.pruned_library(out, shelf)
    assert calls == []
    library.unlink()
    compiled, use = receiver.pruned_library(out, shelf)
    assert compiled == out / "fine-build/fine_search.so" and use["mode"] == "compiled"
    assert use["command"] == ["qualified compiler"] and calls == [compiled.parent]


def test_pruned_runtime_checks_source_and_numpy_version(tmp_path, monkeypatch):
    import numpy

    from leo.analysis.starlink import acquisition

    assert receiver.fine_search_for({}, {}) is None
    with pytest.raises(ValueError, match="unqualified for producer"):
        receiver.pruned_fine_evidence(tmp_path)
    source = Path(acquisition.__file__)
    root = source.parents[3]
    monkeypatch.setattr(receiver, "ROW_SELECTOR_PRODUCERS", {root: receiver._sha(source)})
    evidence = receiver.pruned_fine_evidence(root)
    assert evidence["sources"][str(source)] == receiver._sha(source)
    assert evidence["qualification_sha256"] == receiver.FINE_QUALIFICATION
    lock = dict(producer=str(root), fine_search=evidence)
    monkeypatch.setattr(numpy, "__version__", "unqualified")
    with pytest.raises(ValueError, match="unqualified NumPy"):
        receiver.fine_search_for(lock, {})
    with pytest.raises(ValueError, match="differs from the source seal"):
        receiver.fine_search_for(dict(lock, fine_search=dict(evidence, version="other")), {})


def test_fine_worker_fallback_counts_bind_to_cpu_and_source(tmp_path):
    assert receiver.fine_worker_receipt(tmp_path, 3, "sealed") is None
    record = dict(
        cpu=3, source_lock_sha256="sealed", compatible=True, pruned_calls=2, installed_fallbacks=1
    )
    (tmp_path / "cpu-3.log").write_text(
        "other diagnostics\n" + receiver.FINE_TRACE + json.dumps(record)
    )
    assert receiver.fine_worker_receipt(tmp_path, 3, "sealed") == record
    with pytest.raises(ValueError, match="differs from the source seal"):
        receiver.fine_worker_receipt(tmp_path, 3, "wrong")
