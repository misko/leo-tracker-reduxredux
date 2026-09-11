import time
from contextlib import contextmanager
from types import SimpleNamespace

from leo.cli import scanner_refinement as cli
from leo.storage.scanner_refinement import ScannerRefinementStore
from tests.scanner.refinement_fixtures import comparison_fixture


def test_checkpoint_resumes_without_repeating_completed_probes(monkeypatch, tmp_path):
    fixture = comparison_fixture()
    reads = []

    @contextmanager
    def source(root, session):
        def read(key):
            reads.append(key)
            return key

        yield SimpleNamespace(
            session_kind="fixed",
            input_manifest_sha256=fixture.input_manifest_sha256,
            sample_rate_hz=5000000,
            probe_ids=fixture.scheduled_probe_ids,
            read_probe=read,
        )

    monkeypatch.setattr(cli, "comparison_source", source)
    # Patch only the numerical function body; inspect still binds a real source file.
    monkeypatch.setattr(cli, "compare_probe", lambda _: fixture.rows)
    assert cli.run_session(tmp_path, "scan-one", time.monotonic() - 1) == "partial"
    assert reads == []
    assert cli.run_session(tmp_path, "scan-one", time.monotonic() + 60) == "complete"
    assert len(reads) == 1
    assert cli.run_session(tmp_path, "scan-one", time.monotonic() + 60) == "complete"
    assert len(reads) == 1
    assert ScannerRefinementStore(tmp_path).status("scan-one").manifest.completed_probes == 1
