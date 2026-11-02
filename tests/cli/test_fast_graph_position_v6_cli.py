"""ALGO07 CLI delegates through its versioned public store."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.cli import fast_graph_position_v6 as cli


def test_once_consumes_only_cutoff_qualified_source_and_uses_v7_worker(monkeypatch, tmp_path):
    calls = []

    class Store:
        def __init__(self, root):
            assert root == tmp_path

        @contextmanager
        def owner(self, key):
            assert key == "watcher"
            yield True

        def inputs(self, *, minimum_completed_utc_ns):
            assert minimum_completed_utc_ns == 123
            return [dict(job_id="new", source_job=dict(job_id="old"))]

        def status(self, _):
            return None

    def process(job, **kwargs):
        calls.append((job, kwargs))
        return dict(job_id=job["job_id"], state="complete")

    monkeypatch.setattr(cli, "FastGraphPositionStoreV6", Store)
    monkeypatch.setattr(cli, "process", process)
    cli.watch(SimpleNamespace(bulk_root=tmp_path, minimum_completed_utc_ns=123,
                              source_job="old", once=True, maximum_seconds=20))
    assert len(calls) == 1
    command = calls[0][1]["command"]
    assert Path(command[2]).name == "algo07_production_worker.py"
    assert command[3:] == ["--bulk-root", str(tmp_path)]
    assert calls[0][1]["maximum_seconds"] == 20


@pytest.mark.parametrize("extra", [[], ["--minimum-completed-utc-ns", "0"],
                                  ["--minimum-completed-utc-ns", "1", "--source-job", "old"]])
def test_cli_requires_activation_cutoff_and_bounded_canary(monkeypatch, tmp_path, extra):
    monkeypatch.setattr("sys.argv", ["worker", "--bulk-root", str(tmp_path), *extra])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 2
