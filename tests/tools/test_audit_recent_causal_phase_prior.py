import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).parents[2] / "tools/research/audit_recent_causal_phase_prior.py"
SPEC = importlib.util.spec_from_file_location("audit_recent_causal_phase_prior", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def row(text, epoch, collected):
    return {"text": text, "epoch_utc_ns": epoch, "first_collected_utc_ns": collected}


def test_history_support_is_strictly_causal_and_requires_bounded_predecessor():
    hour = MODULE.NS_HOUR
    current = "1 current\n2 current"
    records = [
        row("1 old\n2 old", 10 * hour, 11 * hour),
        row(current, 20 * hour, 21 * hour),
        row("1 future\n2 future", 30 * hour, 31 * hour),
    ]
    supported = MODULE.history_support(records, current, 25 * hour)
    assert supported["status"] == "supported"
    assert supported["gap_h"] == 10
    assert (
        MODULE.history_support(records, current, 20 * hour)["status"]
        == "current-causal-element-absent"
    )


def test_history_support_declares_zero_fallback_for_missing_or_old_history():
    hour = MODULE.NS_HOUR
    current = "1 current\n2 current"
    assert MODULE.history_support([], current, 100 * hour)["predicted_phase_fallback_s"] == 0
    records = [row("1 old\n2 old", hour, 2 * hour), row(current, 80 * hour, 81 * hour)]
    result = MODULE.history_support(records, current, 90 * hour)
    assert result["status"] == "predecessor-gap-outside-1-to-72-hours"
    assert result["predicted_phase_fallback_s"] == 0


def test_later_same_epoch_revision_does_not_hide_causal_current_element():
    hour = MODULE.NS_HOUR
    current = "1 current\n2 current"
    records = [
        row("1 old\n2 old", 10 * hour, 11 * hour),
        row(current, 20 * hour, 21 * hour),
        row("1 revised\n2 revised", 20 * hour, 22 * hour),
    ]
    assert MODULE.history_support(records, current, 25 * hour)["status"] == "supported"


@pytest.mark.parametrize("cutoff", [100, 101])
def test_prior_rejects_training_at_or_after_first_capture(cutoff):
    prior = {
        "frozen_model": {
            "training_cutoff_utc_ns": cutoff,
            "winner": {"validation_rms_rate_error_s_h": 0.09},
        }
    }
    with pytest.raises(ValueError, match="precede every capture"):
        MODULE.validate_prior(prior, 100)


@pytest.mark.parametrize("sigma", [0, -1, float("nan"), float("inf")])
def test_prior_rejects_invalid_uncertainty(sigma):
    prior = {
        "frozen_model": {
            "training_cutoff_utc_ns": 99,
            "winner": {"validation_rms_rate_error_s_h": sigma},
        }
    }
    with pytest.raises(ValueError, match="finite and positive"):
        MODULE.validate_prior(prior, 100)


def test_prior_preserves_frozen_valid_model():
    winner = {"validation_rms_rate_error_s_h": 0.09176615913014215}
    prior = {"frozen_model": {"training_cutoff_utc_ns": 99, "winner": winner}}
    assert MODULE.validate_prior(prior, 100) is winner
