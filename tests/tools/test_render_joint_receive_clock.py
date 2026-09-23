import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "clock_render", Path(__file__).parents[2] / "reports/render_joint_receive_clock.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_seal_keeps_failed_optimization_and_rejects_tampering(tmp_path):
    nominal = tmp_path / "nominal.json"
    nominal.write_text(json.dumps({"position_truth_used": False}))
    clock = tmp_path / "clock.json"
    clock.write_text("{}")
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "complete": True,
                "qualification": "insufficient",
                "truth_accessed": False,
                "known_position_used": False,
                "refinement_digest": module.digest(nominal),
                "clock_audit_digest": module.digest(clock),
            }
        )
    )
    result.with_suffix(".sha256").write_text(module.digest(result).removeprefix("sha256:"))
    _, docs = module.seal_inputs([result], nominal, clock, tmp_path / "sealed")
    assert docs[0]["qualification"] == "insufficient"
    result.write_text(result.read_text() + " ")
    with pytest.raises(ValueError, match="checksum"):
        module.seal_inputs([result], nominal, clock, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_truth_conditioned_baseline_rejected_before_any_output(tmp_path):
    nominal = tmp_path / "nominal.json"
    nominal.write_text(json.dumps({"position_truth_used": True}))
    with pytest.raises(ValueError, match="blind nominal"):
        module.seal_inputs([], nominal, tmp_path / "not-read.json", tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()
