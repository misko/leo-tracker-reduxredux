import json

import numpy as np
from anchors import select_anchors


class SyntheticData:
    def __init__(self, times, measured, receiver, channel, group, predictions, visible, tracks):
        self.times = np.asarray(times, dtype=float)
        self.measured = np.asarray(measured, dtype=float)
        self.rf = np.full(len(self.times), 11.0e9)
        self.receiver = np.asarray(receiver)
        self.channel = np.asarray(channel)
        self.group = np.asarray(group)
        self.predictions = np.asarray(predictions, dtype=float)
        self.visibility = np.asarray(visible, dtype=bool)
        self.numbers = np.arange(10000, 10000 + self.predictions.shape[1])
        self.tracks = tracks
        self.predict_calls = 0

    def predict(self, parameters, rows=None, satellites=None):
        assert rows is not None and satellites is not None
        self.predict_calls += 1
        return self.predictions[rows, satellites], self.visibility[rows, satellites]


def make_data(specifications, satellite_count=3):
    times = []
    measured = []
    receivers = []
    channels = []
    groups = []
    predictions = []
    visibility = []
    tracks = []
    for track_index, specification in enumerate(specifications):
        start = len(times)
        track_times = np.asarray(specification["times"], dtype=float)
        count = len(track_times)
        track_measured = np.asarray(specification.get("measured", np.zeros(count)), dtype=float)
        track_predictions = np.asarray(specification["predictions"], dtype=float)
        track_visibility = np.asarray(
            specification.get("visible", np.ones_like(track_predictions, dtype=bool)), dtype=bool
        )
        assert track_predictions.shape == (count, satellite_count)
        times.extend(track_times)
        measured.extend(track_measured)
        receivers.extend([specification.get("receiver", 0)] * count)
        channels.extend([specification.get("channel", track_index)] * count)
        groups.extend(specification.get("groups", np.arange(count) + 100 * track_index))
        predictions.extend(track_predictions)
        visibility.extend(track_visibility)
        tracks.append(
            {
                "track_id": specification.get("track_id", f"track-{track_index}"),
                "rows": np.arange(start, start + count),
                "candidate_indices": np.arange(satellite_count),
            }
        )
    return SyntheticData(
        times, measured, receivers, channels, groups, predictions, visibility, tracks
    )


def distinct_predictions(count, best=0, residual=20.0):
    values = np.full((count, 3), -1800.0)
    values[:, best] = -residual
    return values


def test_long_ambiguous_track_loses_to_shorter_distinct_track():
    long_ambiguous = np.full((20, 64), -1800.0)
    long_ambiguous[:, 0] = -20.0
    long_ambiguous[:, 63] = -80.0
    short_distinct = np.full((10, 64), -1800.0)
    short_distinct[:, 0] = -20.0
    data = make_data(
        [
            {
                "track_id": "long-ambiguous",
                "times": np.arange(20),
                "predictions": long_ambiguous,
            },
            {
                "track_id": "short-distinct",
                "times": np.arange(10),
                "predictions": short_distinct,
            },
        ],
        satellite_count=64,
    )

    result = select_anchors(data, np.zeros(70))

    assert [track["track_id"] for track in result["tracks"]] == ["short-distinct"]
    assert np.all(result["satellites"] == 0)
    assert data.predict_calls == 2
    rejected = {row["track_id"]: row for row in result["diagnostics"]["rejected"]}
    assert "runner_up_too_close" in rejected["long-ambiguous"]["rejected_reasons"]
    assert rejected["long-ambiguous"]["runner_up"]["separation_hz"] < 150
    assert rejected["long-ambiguous"]["candidate_count"] == 64


def test_duplicate_source_alternatives_use_one_deterministic_original_row():
    group_times = np.array([0.1, 0.2, 1.1, 2.1, 3.1, 4.1, 5.1, 8.1])
    times = np.repeat(group_times, 2)
    groups = np.repeat(np.arange(8), 2)
    measured = np.tile([25.0, 500.0], 8)
    predictions = np.full((16, 3), -1800.0)
    predictions[:, 0] = 0.0
    data = make_data(
        [
            {
                "track_id": "duplicates",
                "times": times,
                "groups": groups,
                "measured": measured,
                "predictions": predictions,
            }
        ]
    )
    original = data.measured.copy()

    result = select_anchors(data, np.zeros(70))

    assert result["rows"].tolist() == list(range(0, 16, 2))
    assert len(np.unique(data.group[result["rows"]])) == len(result["rows"])
    np.testing.assert_array_equal(data.measured, original)
    np.testing.assert_allclose(result["weights"][:2], [0.5, 0.5])
    assert result["weights"].sum() == 7
    assert result["tracks"][0]["effective_groups"] == 7
    json.dumps(result["tracks"])
    json.dumps(result["diagnostics"])


def test_visibility_gate_abstains_instead_of_forcing_a_track():
    visible = np.ones((12, 3), dtype=bool)
    visible[6:, 0] = False
    visible[:, 1:] = False
    data = make_data(
        [
            {
                "track_id": "mostly-invisible",
                "times": np.arange(12),
                "predictions": distinct_predictions(12),
                "visible": visible,
            }
        ]
    )

    result = select_anchors(data, np.zeros(70))

    assert not len(result["rows"])
    reasons = result["diagnostics"]["rejected"][0]["rejected_reasons"]
    assert "insufficient_visibility" in reasons
    assert "insufficient_supported_fraction" in reasons


def test_receiver_coverage_and_gap_aware_duration():
    data = make_data(
        [
            {
                "track_id": "rx0-best",
                "times": np.arange(14),
                "receiver": 0,
                "predictions": distinct_predictions(14, residual=15),
            },
            {
                "track_id": "rx0-second",
                "times": np.arange(13),
                "receiver": 0,
                "predictions": distinct_predictions(13, residual=25),
            },
            {
                "track_id": "rx1-gapped",
                "times": [0, 1, 2, 3, 20, 21, 22, 23, 24, 25, 26, 27],
                "receiver": 1,
                "predictions": distinct_predictions(12, residual=30),
            },
        ]
    )

    result = select_anchors(data, np.zeros(70), max_tracks=2)

    assert {track["receiver"] for track in result["tracks"]} == {0, 1}
    gapped = next(track for track in result["tracks"] if track["track_id"] == "rx1-gapped")
    assert gapped["duration_s"] == 27
    assert gapped["supported_duration_s"] == 10
    assert gapped["maximum_support_gap_s"] == 17
    assert "rx0-second" in {row["track_id"] for row in result["diagnostics"]["rejected"]}


def test_overlapping_whole_tracks_are_group_exclusive():
    data = make_data(
        [
            {
                "track_id": "preferred",
                "times": np.arange(12),
                "groups": np.arange(12),
                "predictions": distinct_predictions(12, residual=10),
            },
            {
                "track_id": "overlap",
                "times": np.arange(11),
                "groups": np.arange(6, 17),
                "predictions": distinct_predictions(11, residual=20),
            },
        ]
    )

    result = select_anchors(data, np.zeros(70))

    assert [track["track_id"] for track in result["tracks"]] == ["preferred"]
    rejected = result["diagnostics"]["rejected"][0]
    assert rejected["track_id"] == "overlap"
    assert rejected["rejected_reasons"] == ["group_conflict"]
    assert rejected["conflicting_group_count"] == 6
