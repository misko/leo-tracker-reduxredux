from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from verified_source_audit import SourceAudit, summarize


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
