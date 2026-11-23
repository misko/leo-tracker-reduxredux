from importlib import import_module
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module


def test_probe_comparison_rejects_different_support_or_order(research, monkeypatch):
    scoring = research("dense_full_short_raw_score")
    monkeypatch.setattr(scoring, "COUNTS", {"processed": 1})
    before = [{"receiver_id": arm, "valid_start_counter": 12, "candidates": [{"rank": 0}]} for arm in (0, 1)]
    changed = [dict(probe, candidates=[]) for probe in before]
    assert scoring.probe_metadata(before, changed)
    assert not scoring.probe_metadata(before, changed[::-1])
    assert not scoring.probe_metadata(before, [dict(changed[0], valid_start_counter=13), changed[1]])
    assert not scoring.probe_metadata(before, changed[:1])


@pytest.mark.parametrize("status", (0, 1, "timeout"))
def test_external_clock_records_exit_before_any_evidence_review(research, monkeypatch, tmp_path, status):
    trial = research("dense_full_short_raw")
    samples = iter([dict(cpu_s=1., input_blocks=2), dict(cpu_s=2.5, input_blocks=5)])
    monkeypatch.setattr(trial, "usage", lambda: next(samples))

    def child(command, *, timeout, **kwargs):
        assert timeout == 240
        if status == "timeout":
            raise subprocess.TimeoutExpired(command, timeout)
        return SimpleNamespace(returncode=status, stderr="")

    monkeypatch.setattr(trial.subprocess, "run", child)
    clocks = tmp_path / "process.json"
    result = trial.launch(["frozen-worker"], {}, clocks)
    assert json.loads(clocks.read_bytes()) == result
    assert result["status"] == status
    assert result["cpu_s"] == 1.5 and result["input_blocks"] == 3
    assert result["elapsed_s"] >= 0.
