"""Report-only integrity admission cannot open references on changed sources."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("group", ["source_sha256", "input_sha256"])
def test_tampered_authority_blocks_reference_access(tmp_path, monkeypatch, group):
    spec = importlib.util.spec_from_file_location(
        "report129_integrity_test", Path(__file__).with_name("report_cohort.py")
    )
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    artifact = tmp_path / "bound.txt"
    artifact.write_text("original")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    protocol = tmp_path / "protocol.json"
    plan = dict(source_sha256={}, input_sha256={})
    plan[group]["bound.txt"] = expected
    protocol.write_text(json.dumps(plan))
    artifact.write_text("tampered")
    monkeypatch.setattr(report, "ROOT", tmp_path)
    monkeypatch.setattr(
        report, "load_rows", lambda *a, **k: pytest.fail("Receipt load must not start")
    )
    monkeypatch.setattr(
        report,
        "evaluation_callback",
        lambda *a, **k: pytest.fail("Reference port must remain closed"),
    )
    monkeypatch.setattr(sys, "argv", ["report", "--protocol", str(protocol)])
    with pytest.raises(ValueError, match="reporting authority changed"):
        report.main()
