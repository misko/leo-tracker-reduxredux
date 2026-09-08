from copy import deepcopy

import pytest

from tools.verify_presence_window_rank import BINS, TIMINGS, verify


def fixture():
    spec = {"rate_hz": 2500000, "edge": 0, "counter": str(10**16 + 37), "kind": "saved_iq"}
    rows = [
        {
            **spec,
            "bins": bins,
            "iteration": iteration,
            "scores": [0.1] * 6,
            "order": list(range(6)),
            "projected_epoch_samples": [0] * 6,
            **dict.fromkeys(TIMINGS, 1.0),
        }
        for bins in BINS
        for iteration in range(20)
    ]
    return [spec], rows


def test_every_replay_and_large_integer_identity_is_accounted():
    spec, rows = fixture()
    result = verify(rows, rows[::-1], spec)
    assert result["verified_results"] == 100
    assert result["maximum_score_difference"] == 0
    assert result["statistics"]["saved_iq"]["2500000"]["512"]["executions"] == 20


@pytest.mark.parametrize(
    "damage", ["missing", "duplicate", "counter", "order", "epoch", "score", "nan", "time"]
)
def test_malformed_misassociated_or_different_output_never_passes(damage):
    spec, rows = fixture()
    arm = deepcopy(rows)
    if damage == "missing":
        arm.pop()
    elif damage == "duplicate":
        arm.append(arm[0])
    elif damage == "counter":
        arm[0]["counter"] = float(arm[0]["counter"])
    elif damage == "order":
        arm[0]["order"] = [1, 0, 2, 3, 4, 5]
    elif damage == "epoch":
        arm[0]["projected_epoch_samples"][0] = 1
    elif damage in ("score", "nan"):
        arm[0]["scores"][0] = 0.5 if damage == "score" else float("nan")
    else:
        arm[0]["total_cpu_ms"] = -1
    with pytest.raises(ValueError):
        verify(rows, arm, spec)
