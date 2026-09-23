"""Geographic reference evaluation must follow inference validation."""

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("pilot_evaluation_gate", HERE / "evaluate_pilot.py")
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)


@pytest.mark.parametrize("valid_seal", [False, True])
def test_unconverged_or_unsealed_result_cannot_use_reference(monkeypatch, tmp_path, valid_seal):
    inference = HERE / "results/pilot-60-evaluations.json"
    seal = hashlib.sha256(inference.read_bytes()).hexdigest() if valid_seal else "0" * 64
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate",
            "--inference",
            str(inference),
            "--sha256",
            seal,
            "--output-dir",
            str(tmp_path),
        ],
    )

    def forbidden(*args):
        raise AssertionError("reference accessed before validation passed")

    monkeypatch.setattr(EVALUATOR, "distance_m", forbidden)
    with pytest.raises(ValueError, match="convergence|seal"):
        EVALUATOR.main()
    assert not (tmp_path / "evaluation.json").exists()
