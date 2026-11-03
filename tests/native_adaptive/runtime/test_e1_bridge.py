"""Input-authority and empty-result behavior of the recorded E1 harness."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def setup_bridge(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "e1_check", ROOT / "tools/native_adaptive_e1_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = tmp_path / "raw"
    raw.write_bytes(bytes(8))
    digest = hashlib.sha256(raw.read_bytes()).hexdigest()
    template = tmp_path / "template"
    template.write_bytes(bytes(16))
    binary = tmp_path / "binary"
    binary.write_text("test double; never executed")
    meta = dict(raw_sha256=digest, visit_index=0)
    schedule = tmp_path / "schedule"
    schedule.write_text(f"0\t1000\t120\t120\t{template}\t{template}\t{raw}\t{json.dumps(meta)}\n")
    selection = tmp_path / "selection"
    selection.write_text(
        json.dumps(
            dict(
                manifest_sha256="sha256:" + "a" * 64,
                rows=[dict(raw_sha256=digest, rate_hz=1000, sample_start_counter=100)],
            )
        )
    )
    authority = tmp_path / "authority"
    authority.write_text(
        "\n".join(
            json.dumps(
                dict(
                    source=dict(
                        visit=0,
                        receiver=rx,
                        probe_index=0,
                        rate=1000,
                        window_counter=100,
                        input_digest="sha256:" + "a" * 64,
                    )
                )
            )
            for rx in range(2)
        )
    )
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "e1_check",
            "--detector",
            str(binary),
            "--projector",
            str(binary),
            "--replay-manifest",
            str(schedule),
            "--selection-manifest",
            str(selection),
            "--source-authority",
            str(authority),
            "--output",
            str(output),
        ],
    )
    return module, raw, meta, output


def test_rejects_corrupted_iq_before_invoking_inference(tmp_path, monkeypatch):
    module, raw, _, _ = setup_bridge(tmp_path, monkeypatch)
    raw.write_bytes(b"corrupt")
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("inference was invoked")
    )
    with pytest.raises(ValueError, match="IQ authority mismatch"):
        module.main()


def test_zero_candidates_preserves_empty_projection_input(tmp_path, monkeypatch):
    module, _, meta, output = setup_bridge(tmp_path, monkeypatch)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            result = dict(
                result=dict(
                    kind="call",
                    metadata=json.dumps(meta),
                    rate_hz=1000,
                    rows=[
                        dict(receiver_id=rx, probe_index=0, probe_start_ms=0, candidates=[])
                        for rx in range(2)
                    ],
                )
            )
            return subprocess.CompletedProcess(argv, 0, json.dumps(result) + "\n", "")
        assert kwargs["input"] == ""
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    module.main()
    report = json.loads(output.read_text())
    assert report["status"] == "pass"
    assert report["candidates"] == report["observations"] == 0
    assert len(calls) == 2
