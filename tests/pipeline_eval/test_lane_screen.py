import math

import pytest

from tools.pipeline_eval.qualification.lane_screen_eval import check_lane_pair, frozen_threshold
from tools.pipeline_eval.variants.lane_screen import FLOOR, LaneScreen


def test_threshold_uses_worst_authentic_positive_and_conservative_slack():
    scores = [
        {"edge": "lower", "coarse_max": 0.18},
        {"edge": "upper", "coarse_max": 0.17},
        {"edge": "upper", "coarse_max": 0.21},
    ]
    assert frozen_threshold(scores) == FLOOR
    assert frozen_threshold(scores[:1], min_positives=1) == FLOOR
    assert frozen_threshold(scores, min_positives=3) == pytest.approx(FLOOR + 0.8 * (0.17 - FLOOR))


def test_threshold_rejects_impossible_authenticated_stock_positive():
    with pytest.raises(ValueError, match="stock coarse floor"):
        frozen_threshold(
            [{"edge": "lower", "coarse_max": 0.13}, {"edge": "upper", "coarse_max": 0.18}],
            min_positives=2,
        )


def test_screen_decisions_are_physical_lane_specific_and_strict():
    def row(receiver):
        return dict(receiver_id=receiver, candidate_count=0, fine_precision_calls=0, candidates=[])

    stock = [row(0), row(1)]
    screen = [row(0), row(1)]
    scores = [{"coarse_max": 0.15, "rejected": True}, {"coarse_max": 0.17, "rejected": False}]
    checked = check_lane_pair(stock, screen, scores, 0.17)
    assert [lane["rejected"] for lane in checked] == [True, False]
    screen[1]["fine_precision_calls"] = 1
    with pytest.raises(ValueError, match="admitted by the screen changed"):
        check_lane_pair(stock, screen, scores, 0.17)


@pytest.mark.parametrize("threshold", [math.nan, math.inf, -0.01, 1.01])
def test_invalid_thresholds_fail_before_native_entry(threshold):
    port = object.__new__(LaneScreen)
    with pytest.raises(ValueError, match="coarse activity threshold"):
        port.analyze(None, threshold)
