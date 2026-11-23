from importlib import import_module
from hashlib import sha256
from pathlib import Path
import sys


def test_trace_attributes_first_load_and_actual_compilation_once(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    trace = import_module("active_imports").ImportTrace()
    (tmp_path / "_weak_trace_parent.py").write_text("import _weak_trace_child\n")
    (tmp_path / "_weak_trace_child.py").write_text("value = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        with trace.scope():
            import_module("_weak_trace_parent")
            import_module("_weak_trace_parent")
        parent, child = [row for row in trace.modules if row["name"].startswith("_weak_trace_")]
        assert child["parent"] == parent["index"]
        assert parent["cpu_ns"] == parent["exclusive_cpu_ns"] + child["cpu_ns"]
        assert all(row["exclusive_cpu_ns"] >= 0 for row in (parent, child))
        assert sorted(row["name"] for row in trace.compiles if row["name"].startswith("_weak_trace_")) == [
            "_weak_trace_child", "_weak_trace_parent"
        ]
    finally:
        sys.modules.pop("_weak_trace_parent", None)
        sys.modules.pop("_weak_trace_child", None)


def test_deferred_detector_keeps_original_implementation_on_first_call(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    module = import_module("lazy_scanner_detector")
    scanner = tmp_path / "_lazy_detector_scan.py"
    receiver = tmp_path / "_lazy_detector_receiver.py"
    scanner.write_bytes(b"from _lazy_detector_receiver import detector\nidentity = 'released'\n")
    receiver.write_bytes(b"def detector(x, *, scale):\n    return x*scale\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    audit = {"deferred": False, "original_calls": 0}
    finder = module.DetectorFinder(scanner.stem, receiver.stem, scanner, sha256(scanner.read_bytes()).hexdigest(),
                                   receiver, sha256(receiver.read_bytes()).hexdigest(), audit)
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    try:
        loaded = import_module(scanner.stem)
        assert receiver.stem not in sys.modules and loaded.identity == "released"
        assert audit == {"deferred": True, "original_calls": 0}
        assert loaded.detector(5, scale=3) == 15
        assert receiver.stem in sys.modules and audit["original_calls"] == 1
    finally:
        sys.modules.pop(scanner.stem, None)
        sys.modules.pop(receiver.stem, None)


def test_unreviewed_file_uses_original_importer(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    module = import_module("lazy_scanner_detector")
    scanner = tmp_path / "_lazy_detector_unreviewed_scan.py"
    receiver = tmp_path / "_lazy_detector_unreviewed_receiver.py"
    scanner.write_bytes(b"from _lazy_detector_unreviewed_receiver import detector\n")
    receiver.write_bytes(b"def detector():\n    return 'stock'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    audit = {"deferred": False, "original_calls": 0}
    finder = module.DetectorFinder(scanner.stem, receiver.stem, scanner, "wrong", receiver, "wrong", audit)
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    try:
        loaded = import_module(scanner.stem)
        assert receiver.stem in sys.modules and loaded.detector() == "stock"
        assert audit["fallback"] == "unreviewed scanner or receiver source" and not audit["deferred"]
    finally:
        sys.modules.pop(scanner.stem, None)
        sys.modules.pop(receiver.stem, None)
