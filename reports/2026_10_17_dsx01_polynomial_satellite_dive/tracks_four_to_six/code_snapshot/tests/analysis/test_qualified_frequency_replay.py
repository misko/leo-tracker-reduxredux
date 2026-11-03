"""Measurement refinement preserves ownership and cannot choose aliases by fit."""

from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.research.qualified_frequency_replay import replay_qualified_frequencies


def fixture():
    track = dict(
        key="track",
        receiver=1,
        channel=2,
        times=np.arange(3.0),
        values=np.array([100.0, 200.0, 300.0]),
        observation_ids=["a", "b", "c"],
    )
    rows = [
        dict(
            observation_id=oid,
            component="track",
            receiver=1,
            channel=2,
            time_s=float(i),
            graph_cfo_hz=float(track["values"][i]),
            original_glrt_cfo_hz=float(track["values"][i]),
            supported_branches=1,
            best_supported=True,
            best_alias=0,
            branches=[
                dict(
                    alias=0,
                    measurement_supported=True,
                    absolute_cfo_hz=float(track["values"][i] + 10),
                )
            ],
        )
        for i, oid in enumerate(track["observation_ids"])
    ]
    rows[1].update(supported_branches=0, best_supported=False)
    rows[1]["branches"][0]["measurement_supported"] = False
    rows[2]["branches"].append(
        dict(alias=1, measurement_supported=True, absolute_cfo_hz=300.0 + 1 / 4.4e-6)
    )
    rows[2]["supported_branches"] = 2
    return [track], rows


def test_only_unique_supported_measurement_changes_frequency_with_all_ids_retained():
    tracks, rows = fixture()
    new, info = replay_qualified_frequencies(tracks, rows)
    np.testing.assert_array_equal(new[0]["values"], [110, 200, 300])
    np.testing.assert_array_equal(tracks[0]["values"], [100, 200, 300])
    assert new[0]["observation_ids"] == tracks[0]["observation_ids"]
    np.testing.assert_array_equal(new[0]["times"], tracks[0]["times"])
    assert info["original_points"] == 3 and info["points_dropped"] == 0
    assert set(info["status_counts"].values()) == {1}


@pytest.mark.parametrize("fault", ["missing", "duplicate", "unknown", "frequency", "time"])
def test_bad_binding_cannot_silently_drop_or_replace_points(fault):
    tracks, rows = fixture()
    rows = deepcopy(rows)
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(rows[0])
    elif fault == "unknown":
        rows[0]["observation_id"] = "unknown"
    elif fault == "frequency":
        rows[0]["graph_cfo_hz"] = 101.0
    else:
        rows[0]["time_s"] = 10.0
    with pytest.raises(ValueError):
        replay_qualified_frequencies(tracks, rows)
