import archive_results
import pytest
import report


def test_explicit_paths_and_lineage(monkeypatch, tmp_path):
    labels = [f"m{i}" for i in range(12)]
    plan = dict(
        members=[dict(label=x) for x in labels],
        predecessor_failures=[
            dict(label=x, elapsed_s=0.1, receipt=f"original/{x}.json") for x in labels
        ],
    )
    calls = []

    def load(here, root):
        calls.append((here, root))
        return plan, {}, {"receipt": "hash"}

    monkeypatch.setitem(report.API, "load", load)
    monkeypatch.setitem(report.API, "summarize", lambda *args: dict(runtime_s=20, complete=True))
    monkeypatch.setitem(report.API, "sha", lambda path: "successor")
    result = report.prepare(tmp_path, tmp_path.parent)
    assert calls == [(tmp_path, tmp_path.parent)]
    assert result["lineage_elapsed_s"] == pytest.approx(21.2)
    assert result["predecessor_elapsed_s"] == pytest.approx(1.2)
    assert result["protocol_sha256"] == "successor"
    plan["predecessor_failures"].pop()
    with pytest.raises(ValueError, match="predecessor coverage"):
        report.prepare(tmp_path, tmp_path.parent)


def test_archive_paths_explicit_and_gate_first(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(archive_results, "prepare", lambda *args: calls.append(("gate", args)))
    monkeypatch.setitem(
        archive_results.API, "create", lambda *args: calls.append(("archive", args))
    )
    archive_results.create(tmp_path, tmp_path.parent)
    assert calls == [
        ("gate", (tmp_path, tmp_path.parent)),
        ("archive", (tmp_path, tmp_path.parent)),
    ]
