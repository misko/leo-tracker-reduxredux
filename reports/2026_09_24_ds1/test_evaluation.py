"""Evaluation must reject altered or non-training-selected inference."""

import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "ds1_eval_test", Path(__file__).with_name("evaluate.py")
)
EVAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVAL)


def fixture():
    zero = {"tau_s": 0, "training_capped_loss": 0.2, "latitude_deg": 1, "longitude_deg": 2}
    shifted = {"tau_s": -1, "training_capped_loss": 0.1, "latitude_deg": 1, "longitude_deg": 2}
    case = {"case_id": "case", "session_ids": ["recording"]}
    bindings = {"dataset": "sha256:frozen"}
    arm = {
        "complete": True,
        "case_id": "case",
        "prior": "sacramento",
        "bindings": bindings,
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
        "session_bindings": [{"session_id": "recording"}],
        "visited_pairs": [zero, shifted],
        "models": {"baseline": zero, "shared_time": shifted},
    }
    return arm, case, "sacramento", copy.deepcopy(bindings)


def test_valid_train_selected_pair_passes():
    EVAL.validate_arm(*fixture())


@pytest.mark.parametrize("fault", ["binding", "held", "membership", "winner", "tau"])
def test_invalid_inference_rejected_before_reference_scoring(fault):
    arm, case, prior, bindings = fixture()
    if fault == "binding":
        arm["bindings"]["dataset"] = "changed"
    elif fault == "held":
        arm["held_used_for_fit"] = True
    elif fault == "membership":
        arm["session_bindings"][0]["session_id"] = "different"
    elif fault == "winner":
        arm["models"]["shared_time"] = arm["models"]["baseline"]
    else:
        arm["models"]["shared_time"]["tau_s"] = -6
    with pytest.raises(ValueError):
        EVAL.validate_arm(arm, case, prior, bindings)


def test_full_case_failure_preserved_and_unrelated_failure_rejected():
    arm, case, prior, bindings = fixture()
    missing = "scan-hop-6cd2560365a058bc"
    arm["case_id"] = case["case_id"] = "test_20260922_00_all"
    case["session_ids"] = [f"session_{i}" for i in range(64)]
    case["session_ids"][47] = missing
    arm["failure"] = {"session_id": missing, "reason": "missing counter-continuity authority"}
    EVAL.validate_arm(arm, case, prior, bindings)
    arm["failure"]["session_id"] = "unrelated"
    with pytest.raises(ValueError):
        EVAL.validate_arm(arm, case, prior, bindings)


def test_tied_loss_cannot_override_zero_preference():
    arm, case, prior, bindings = fixture()
    arm["models"]["shared_time"]["training_capped_loss"] = 0.2
    with pytest.raises(ValueError, match="deterministic"):
        EVAL.validate_arm(arm, case, prior, bindings)
