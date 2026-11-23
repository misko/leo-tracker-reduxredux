from importlib import import_module
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
