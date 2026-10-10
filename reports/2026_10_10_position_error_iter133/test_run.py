import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("run133_test", Path(__file__).with_name("run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_import_failure_has_terminal_receipt_and_cannot_silently_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run.sys, "argv", ["run.py", "--label", "member-0"])
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    plan = dict(
        maximum_fit_calls=72,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        sources={},
        inputs={},
        members=[dict(label=f"member-{i}") for i in range(12)],
    )
    (tmp_path / "protocol.json").write_text(json.dumps(plan))

    def fail_import(*args):
        raise ImportError("synthetic numerical import failure")

    monkeypatch.setattr(run.runpy, "run_path", fail_import)
    run.main()
    path = tmp_path / "results/member-0.json"
    receipt = json.loads(path.read_text())
    assert receipt["status"] == "failed" and receipt["attempts"] == {}
    assert "synthetic numerical import failure" in receipt["error"]
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        run.main()
    assert path.read_bytes() == before
