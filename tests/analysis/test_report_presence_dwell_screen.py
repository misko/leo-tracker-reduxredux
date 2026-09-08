from copy import deepcopy

import pytest

from tools.report_presence_dwell_screen import control_summary, historic_summary


def test_historic_presence_is_not_association_and_unresolved_is_not_false_alarm():
    row = {
        "mode": "blind",
        "bins": 512,
        "timing_bins": 2048,
        "rate_hz": 2500000,
        "session": "scan",
        "visit": 0,
        "reference_positive": [True] + [False] * 5,
        "observations": [{"detected": True, "associated": False}],
    }
    unresolved = {**deepcopy(row), "visit": 1, "reference_positive": [False] * 6}
    seeded = {**row, "mode": "seeded"}
    result = historic_summary([row, unresolved, seeded])
    assert result == {
        "dwells": 2,
        "reference_positive": 1,
        "reference_positive_flagged": 1,
        "reference_associated": 0,
        "unresolved": 1,
        "unresolved_flagged": 1,
    }
    with pytest.raises(ValueError):
        historic_summary([row, row])


def test_controls_count_only_top_one_and_do_not_hide_failed_negatives():
    row = {
        "truth": {
            "rate_hz": 5000000,
            "edge": "upper",
            "seed": 1,
            "kind": "pilot",
            "window": 0,
            "starlink_model_present": True,
        },
        "flags": [False, True],
    }
    negative = {
        "truth": {**row["truth"], "kind": "tone", "window": None, "starlink_model_present": False},
        "flags": [True, True],
    }
    assert control_summary([row, negative]) == {
        "positive": 1,
        "positive_flagged": 0,
        "negative": 1,
        "negative_flagged": 1,
    }
    with pytest.raises(ValueError):
        control_summary([row, row])
