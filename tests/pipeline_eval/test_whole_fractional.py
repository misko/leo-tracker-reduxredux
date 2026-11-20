import json

import pytest

from tools.pipeline_eval.qualification import fractional_runtime_whole as parity
from tools.pipeline_eval.qualification import full_v5_check, recording_to_v5, secant_end_to_end
from tools.pipeline_eval.qualification import whole_fractional_worker as worker


def test_factor_mismatch_preserves_receipt_and_stops_before_solving(tmp_path, monkeypatch):
    ident = "DS29-0082"
    out = tmp_path / ident
    out.mkdir()
    for lane, cpu in enumerate(worker.CPUS):
        row = dict(
            start=dict(cgroup="/test", cpus=[cpu]),
            end=dict(cgroup="/test", cpus=[cpu]),
            native_timings_s=[(0.017, 0.015)],
        )
        (out / f"replayed-{lane}.jsonl").write_text("{}\n")
        (out / f"replayed-{lane}.log").write_text("whole-lane-result: " + json.dumps(row))
    (out / "capture.json").write_text("{}")
    (out / "raw-worker-exits.json").write_text('{"exit_codes":[0,0]}')
    (tmp_path / "plan.json").write_text(
        json.dumps(dict(inputs={ident: dict(native_sha256="control")}))
    )
    monkeypatch.setattr(worker.raw, "mark", lambda stage: dict(cgroup="/test", stage=stage))
    monkeypatch.setattr(full_v5_check, "_load_case", lambda case: {"id": case})
    monkeypatch.setattr(secant_end_to_end, "capture_duration", lambda document: 300)
    monkeypatch.setattr(
        recording_to_v5,
        "native_document",
        lambda *a: (dict(fresh=True), dict(processed_windows=2)),
    )

    def reject(*args):
        raise ValueError("different valid factor")

    monkeypatch.setattr(parity, "verify_native", reject)
    with pytest.raises(ValueError, match="different valid factor"):
        worker.assemble(out, ident, worker.LIMIT, "ordinary")
    raw = json.loads((out / "raw-stages.json").read_bytes())
    assert raw["factor_parity_error"] == "different valid factor"
    assert raw["control_native_sha256"] == "control"
    assert raw["native_sha256"] == full_v5_check._sha(out / "native.json")
    assert not (out / "position").exists()
