import pytest
from soft_continuation import select_predecessor


def candidate(name, loss, width="medium"):
    return name, {"session": "scan", "tolerance": width, "seed_sha256": "seed",
                  "fit": {"objective": loss}}


def test_predecessor_uses_only_same_width_objective_not_position_error():
    left = candidate("left", 10.)
    right = candidate("right", 9.)
    left[1]["error_km"] = 0.
    right[1]["error_km"] = 100.
    assert select_predecessor([left, right])[0] == "right"


def test_predecessor_rejects_incommensurable_likelihoods_and_no_finite_fit():
    with pytest.raises(ValueError, match="share scan, width"):
        select_predecessor([candidate("left", 10.), candidate("right", 9., "loose")])
    with pytest.raises(ValueError, match="no finite predecessor"):
        select_predecessor([candidate("nan", float("nan"))])
