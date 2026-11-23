import json
from hashlib import sha256

import pytest

from reports.ALGO08.v3.paired_veto_history import PIN, SOURCE, summarize


def test_original_trial_decisions_in_both_orders():
    blob = SOURCE.read_bytes()
    assert sha256(blob).hexdigest() == PIN
    result = summarize(json.loads(blob))
    assert result["cases"] == 410
    assert result["trials"] == 137
    assert result["adopted_recordings"] == 74
    assert result["both_arms_failed_tracks"] == 36


def test_one_failed_fitted_arm_cannot_win_by_score():
    trial = {
        "case": "x",
        "replacements": [1],
        "failed_curved": 0,
        "failed_predictive": 0,
        "paired_valid": False,
        "corrected_loss": 10,
        "RF_gain": 7,
    }
    ledger = {
        "rows": [
            {
                "case": "x",
                "arm": "c0",
                "policy": "equal_assignment_priors",
                "accepted": False,
                "replacements": [],
            }
        ],
        "evaluated_case_ids": ["x"],
        "trials": [
            dict(trial, arm="c0"),
            dict(trial, arm="fitted_c", failed_predictive=1),
        ],
    }
    assert summarize(ledger)["only_fitted_failed_tracks"] == 1
    ledger["trials"][0]["paired_valid"] = True
    with pytest.raises(ValueError, match="conflicting"):
        summarize(ledger)
