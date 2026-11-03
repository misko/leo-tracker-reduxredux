import json

import numpy as np
import pytest
from association import associate
from common import ALIAS_HZ


class SyntheticData:
    def __init__(self, times, measured, prediction, group, receiver=None, channel=None):
        self.times = np.asarray(times, dtype=float)
        self.measured = np.asarray(measured, dtype=float)
        self.rf = np.full(len(self.times), 12.0e9)
        self.receiver = (
            np.zeros(len(self.times), dtype=int) if receiver is None else np.asarray(receiver)
        )
        self.channel = (
            np.zeros(len(self.times), dtype=int) if channel is None else np.asarray(channel)
        )
        self.group = np.asarray(group)
        self.numbers = np.arange(70000, 70000 + np.asarray(prediction).shape[1])
        self._prediction = np.asarray(prediction, dtype=float)
        self._visible = np.ones_like(self._prediction, dtype=bool)

    def predict(self, parameters, rows=None, satellites=None):
        assert parameters == "parameters"
        if rows is not None and satellites is not None:
            return self._prediction[np.asarray(rows), np.asarray(satellites)], self._visible[
                np.asarray(rows), np.asarray(satellites)
            ]
        return self._prediction.copy(), self._visible.copy()


def anchors(rows, satellites, weights=None):
    rows = np.asarray(rows, dtype=int)
    return {
        "rows": rows,
        "satellites": np.asarray(satellites, dtype=int),
        "weights": np.ones(len(rows)) if weights is None else np.asarray(weights, dtype=float),
        "tracks": ["synthetic"],
        "diagnostics": {"source": "test"},
    }


def test_preserves_anchors_and_caps_balanced_extension_weight():
    times = np.repeat(np.arange(0, 16, 2), 2)
    groups = np.repeat(np.arange(8), 2)
    measured = np.tile([20.0, 300.0], 8)
    prediction = np.column_stack([np.zeros(len(times)), np.full(len(times), 5000.0)])
    data = SyntheticData(times, measured, prediction, groups)
    result = associate(data, "parameters", anchors([0], [0], [2.0]))
    assert result["rows"][result["anchor_mask"]].tolist() == [0]
    assert len(np.unique(data.group[result["rows"]])) == len(result["rows"])
    assert len(result["rows"]) == 8
    assert np.all(result["weights"] > 0)
    assert result["weights"][result["anchor_mask"]].sum() == pytest.approx(2.0)
    assert result["weights"][~result["anchor_mask"]].sum() <= 2.0
    assert result["diagnostics"]["extension_weight_cap_respected"]
    json.dumps(result["segments"], allow_nan=False)
    json.dumps(result["diagnostics"], allow_nan=False)


def test_short_distractor_segment_is_not_extended():
    times = np.arange(4, dtype=float) * 2
    prediction = np.zeros((4, 1))
    data = SyntheticData(times, np.zeros(4), prediction, np.arange(4))
    result = associate(data, "parameters", anchors([0], [0]))
    assert result["rows"].tolist() == [0]
    assert result["segments"] == []


def test_tuning_gap_does_not_break_observed_epoch_coherence():
    times = np.r_[np.arange(0, 8, 2), np.arange(100, 108, 2)]
    prediction = np.zeros((8, 1))
    data = SyntheticData(times, np.zeros(8), prediction, np.arange(8))
    result = associate(data, "parameters", anchors([0], [0]))
    assert len(result["rows"]) == 8
    assert result["segments"][0]["span_s"] == 106.0
    assert result["segments"][0]["supported_duration_s"] == 14.0


def test_jittered_alternatives_match_canonical_group_support_without_inflation():
    canonical_times = np.arange(0, 16, 2, dtype=float)
    canonical = SyntheticData(
        canonical_times,
        np.zeros(8),
        np.zeros((8, 1)),
        np.arange(8),
    )
    jittered_times = np.repeat(canonical_times, 2) + np.tile([-0.00045, 0.00045], 8)
    jittered = SyntheticData(
        jittered_times,
        np.zeros(16),
        np.zeros((16, 1)),
        np.repeat(np.arange(8), 2),
    )

    canonical_result = associate(canonical, "parameters", anchors([0], [0]))
    jittered_result = associate(jittered, "parameters", anchors([0], [0]))

    assert len(canonical_result["rows"]) == len(jittered_result["rows"]) == 8
    assert len(np.unique(jittered.group[jittered_result["rows"]])) == 8
    assert canonical_result["segments"][0]["points"] == 8
    assert jittered_result["segments"][0]["points"] == 8
    assert jittered_result["segments"][0]["supported_duration_s"] == pytest.approx(
        canonical_result["segments"][0]["supported_duration_s"]
    )


def test_raw_span_without_supported_duration_does_not_qualify():
    times = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 100.0])
    data = SyntheticData(times, np.zeros(8), np.zeros((8, 1)), np.arange(8))
    result = associate(data, "parameters", anchors([0], [0]))
    assert result["rows"].tolist() == [0]
    assert result["segments"] == []


def test_crossing_abstains_but_simultaneous_distinct_groups_survive():
    epoch_times = np.arange(0, 22, 2, dtype=float)
    times = np.repeat(epoch_times, 2)
    groups = np.arange(len(times))
    sat0 = -1000.0 + 100.0 * times
    sat1 = 1000.0 - 100.0 * times
    prediction = np.column_stack([sat0, sat1])
    measured = np.empty(len(times))
    measured[0::2] = sat0[0::2]
    measured[1::2] = sat1[1::2]
    data = SyntheticData(times, measured, prediction, groups)
    result = associate(data, "parameters", anchors([0, 1], [0, 1]))
    selected_groups = set(data.group[result["rows"]].tolist())
    crossing_groups = set(groups[times == 10.0].tolist())
    assert selected_groups.isdisjoint(crossing_groups)
    for time_s in epoch_times[epoch_times != 10.0]:
        selected = result["rows"][np.isin(result["rows"], np.flatnonzero(times == time_s))]
        assert len(selected) == 2
        assert set(result["satellites"][np.isin(result["rows"], selected)]) == {0, 1}
    assert result["diagnostics"]["ambiguous_groups_rejected"] == 2


def test_anchor_is_fixed_even_when_invisible_and_outside_gate():
    times = np.arange(0, 16, 2, dtype=float)
    prediction = np.zeros((8, 1))
    measured = np.zeros(8)
    measured[4] = 9000.0
    data = SyntheticData(times, measured, prediction, np.arange(8))
    data._visible[4, 0] = False
    result = associate(data, "parameters", anchors([0, 4, 7], [0, 0, 0]))
    anchor_rows = set(result["rows"][result["anchor_mask"]].tolist())
    assert anchor_rows == {0, 4, 7}
    assert len(np.unique(data.group[result["rows"]])) == len(result["rows"])


def test_alias_wrapping_and_allowed_satellite_filter():
    times = np.arange(0, 18, 2, dtype=float)
    measured = np.full(9, ALIAS_HZ + 25.0)
    prediction = np.column_stack([np.zeros(9), np.full(9, 4000.0)])
    data = SyntheticData(times, measured, prediction, np.arange(9))
    result = associate(data, "parameters", anchors([0, 1], [0, 1]), allowed_satellites=[0])
    assert set(result["satellites"][~result["anchor_mask"]]) == {0}
    assert set(result["rows"][result["anchor_mask"]]) == {0, 1}


def test_explicit_allowed_satellite_can_extend_an_unanchored_identity():
    times = np.arange(0, 18, 2, dtype=float)
    prediction = np.column_stack([np.full(9, 5000.0), np.zeros(9)])
    data = SyntheticData(times, np.zeros(9), prediction, np.arange(9))
    result = associate(data, "parameters", anchors([0], [0]), allowed_satellites=[1])
    assert result["rows"][result["anchor_mask"]].tolist() == [0]
    assert set(result["satellites"][~result["anchor_mask"]]) == {1}
    assert result["weights"][~result["anchor_mask"]].sum() <= 1.0


def test_conflicting_anchor_groups_are_rejected():
    data = SyntheticData([0, 0], [0, 0], np.zeros((2, 1)), [4, 4])
    with pytest.raises(ValueError, match="at most once"):
        associate(data, "parameters", anchors([0, 1], [0, 0]))
