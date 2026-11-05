from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.residual_fragments import fragment_rows, runs
from leo.analysis.localization_v3.residual_preflight import preflight, rank_targets


def track(key, times, *, receiver=1, channel=1, rf_hz=11.5e9):
    return dict(
        key=key,
        times=list(times),
        values=[0.0] * len(times),
        receiver=receiver,
        channel=channel,
        rf_hz=rf_hz,
        observation_ids=[f"{key}-{k}" for k in range(len(times))],
    )


def observations(tracks):
    return [
        dict(
            observation_id=o,
            receiver=t["receiver"],
            channel=t["channel"],
            time_s=time,
            measured_cfo_hz=value,
        )
        for t in tracks
        for o, time, value in zip(t["observation_ids"], t["times"], t["values"], strict=True)
    ]


def test_native_adjacency_cannot_bridge_claimed_points_or_source_pieces():
    t = track("a", [0, 1, 2, 3, 4, 5])
    assert runs(t, {"a-2"}) == [[0, 1], [3, 4, 5]]
    t["pieces"] = [dict(indices=[0, 1, 2]), dict(indices=[3, 4, 5])]
    assert runs(t, set()) == [[0, 1, 2], [3, 4, 5]]
    assert runs(track("b", [0, 5, 10.00001]), set()) == [[0, 1], [2]]


def test_only_identical_physical_aliases_collapse_and_conserve_all_points():
    t = track("a", [0, 1, 2, 3])
    alias = dict(t, key="alias", values=[1 / 4.4e-6] * 4)
    obs = observations([t])
    rows, summary = fragment_rows("SCAN", [t, alias], obs, {"a-1": 123}, ["session"])
    assert [r["observation_ids"] for r in rows] == [["a-0"], ["a-2", "a-3"]]
    assert sum(r["points"] for r in rows) == summary["residual_graph_unique_points"] == 3
    assert summary["duplicate_alias_tracks_collapsed"] == 1
    broken = dict(t, observation_ids=["a-0", "other", "a-2", "a-3"])
    with pytest.raises(ValueError, match="Partial graph-source overlap"):
        fragment_rows("SCAN", [t, broken], obs, {})


@pytest.mark.parametrize("failure", ["duplicate", "lane", "time", "unknown_owner"])
def test_native_provenance_mismatches_fail(failure):
    t = track("a", [0, 1, 2])
    obs, owners = observations([t]), {}
    if failure == "duplicate":
        obs.append(dict(obs[0]))
    elif failure == "lane":
        obs[0]["channel"] += 1
    elif failure == "time":
        obs[0]["time_s"] += 1
    else:
        owners["unknown"] = 1
    with pytest.raises(ValueError):
        fragment_rows("SCAN", [t], obs, owners)


def test_ranking_preserves_both_arm_ownership_minimum_evidence_and_cap():
    tracks = [track(str(k), list(np.linspace(0, 20 + k, 21))) for k in range(6)]
    tracks += [
        track("too_short", list(np.linspace(0, 14, 21))),
        track("too_few", list(np.linspace(0, 40, 19))),
    ]
    obs = observations(tracks)
    owners = dict(c0={"5-10": 123}, fitted_c={})
    before = deepcopy((tracks, obs, owners))
    result = rank_targets(tracks, obs, owners, ["session"])
    assert result["eligible_targets"] == 5
    assert [r["key"] for r in result["targets"]] == ["4", "3", "2"]
    assert (tracks, obs, owners) == before
    arrays = deepcopy(tracks)
    for t in arrays:
        t["times"], t["values"] = np.asarray(t["times"]), np.asarray(t["values"])
    assert rank_targets(arrays, obs, owners, ["session"]) == result


def test_preflight_applies_selected_receiver_and_rf_terms_without_changing_state():
    tracks = [track("a", [1, 2, 3]), track("b", [1, 2, 3], receiver=2, rf_hz=23e9)]
    for t in tracks:
        t["times"] = np.asarray(t["times"])
        t["values"] = np.array([20.0, 30.0, 40.0])
    beta = np.array([1.0, 2.0])
    smooth = np.array([[3.0], [4.0]])
    scan = SimpleNamespace(
        tracks=tracks,
        hardware=lambda tr, b: b[tr["receiver"] - 1],
        rx_basis=[np.ones((3, 1))] * 2,
        origin_utc_ns=123,
        sky=dict(time_s=[-40, 340]),
    )
    p = SimpleNamespace(state=lambda x: dict(beta=beta, smooth=smooth))
    d = dict(
        scan=scan,
        problems={a: (p, np.array([0.0, 0.0])) for a in ("c0", "fitted_c")},
        replay_checks={},
    )
    targets = [
        dict(
            track_index=i,
            source_local_indices=[0, 2],
            observation_ids=[t["observation_ids"][k] for k in (0, 2)],
        )
        for i, t in enumerate(tracks)
    ]
    result = preflight(d, targets, dict(origin_utc_ns=123))
    for arm in ("c0", "fitted_c"):
        np.testing.assert_array_equal(result["targets"][0]["corrected_hz"][arm], [16.0, 36.0])
        np.testing.assert_array_equal(result["targets"][1]["corrected_hz"][arm], [10.0, 30.0])
    np.testing.assert_array_equal(beta, [1.0, 2.0])
    np.testing.assert_array_equal(smooth, [[3.0], [4.0]])
    targets[0]["observation_ids"].reverse()
    with pytest.raises(ValueError, match="Native source index mismatch"):
        preflight(d, targets, dict(origin_utc_ns=123))
    with pytest.raises(ValueError, match="metadata origin"):
        preflight(d, targets, dict(origin_utc_ns=124))
