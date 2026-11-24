"""Check exact hardware separation, null opportunities and replay attribution."""

import pytest

from deferred_family_held_support import cohort, deny_raw_and_orbital, native_opportunities, split_runs, time_separated


def test_temporal_embargo_uses_both_acquisition_apertures():
    used = [(100, 120), (115, 140)]
    assert time_separated(85, 2, used, 10)
    assert not time_separated(88, 2, used, 10)
    assert not time_separated(152, 2, used, 10)
    assert time_separated(153, 2, used, 10)


def test_runs_split_at_blocked_rows_and_original_gaps():
    rows = {name: {"start": j} for name, j in zip("abcde", (0, 2, 4, 5, 15), strict=True)}
    assert split_runs(list(rows), rows, set("acde"), 6) == [["a"], ["c", "d"], ["e"]]


def test_signed_lane_opportunities_retain_nondetections():
    def item(receiver, passed):
        return dict(receiver_id=receiver, valid_start_counter=10000, channel=1, actual_rf_hz=1000,
                    candidates=[dict(passed_fractional_margin_gate=passed)])

    actual = native_opportunities(dict(source=dict(session_id="session", probes=[item(0, False), item(1, True)])))
    assert sorted((r["lane"], r["positive"]) for r in actual.values()) == [((1, 1), False), ((2, 1), True)]


def test_coarse_hypothesis_does_not_become_an_owned_assignment():
    opportunities = {str(i): dict(start=i, lane=(2, 1), rf=1000, positive=i < 14) for i in range(15)}
    tracks = [dict(key="component", observation_ids=[str(i) for i in range(12)])]
    prior = ({"component": [2, 481, 1]}, {}, {"component": [5, 2]}, {}, {}, {})
    own = {"c0": {"0": (481, "conditional")}, "fitted_c": {}}
    result = cohort(opportunities, tracks, set(opportunities), 1, 6, prior, (5, 861), own, {})
    assert (result["nondetections"], result["detections_without_graph"], result["candidate_segments"]) == (1, 2, 1)
    assert result["target_candidate_segments"]["target_coarse_salvage"] == 1
    assert result["target_candidate_segments"]["target_elected"] == 0
    assert result["target_observed_in_ordinary_terminal"] == {"c0": 0, "fitted_c": 0}
    assert result["observed_in_ordinary_terminal"]["c0"] == {"conditional": 1}


@pytest.mark.parametrize("path", [b"/dev/shm/example.tle", "/srv/bulk/example/manifest.json", "/tmp/a.ci16.zst"])
def test_scope_excludes_backing_iq_and_orbit_paths(path):
    with pytest.raises(ValueError, match="held-opportunity"):
        deny_raw_and_orbital("open", (path,))
