"""Check the deferred classifier and coverage with synthetic tape rows."""

from copy import deepcopy

import pytest

from deferred_family_nomination import nominate, track_key
from deferred_family_nomination_replay import support_coverage


def row(rx, channel, index, *, closed=False, slope=2.0, profile_noise=True):
    component = f"SCAN-RX{rx}-CH{channel}-T{index:03}-RF1000000.000000"
    local = slope is not None and slope <= 3.0
    tests = dict(profile_rms=True, profile_bias=True, profile_noise=profile_noise,
                 conditional=local, alias=True, visibility=True)
    return dict(component=component, candidate_index=7, norad=100, role="conditional", points=4,
                observation_ids=[f"{component}-{i}" for i in range(4)], actual_tests=tests,
                compatible=all(tests.values()) and not closed, family_support_groups=1 if closed else None,
                conditional=dict(compatible=local, rms_hz=100.0, diagnostics=dict(mean_z=1.0, slope_z=slope,
                    quadratic_bic_gain=1.0, maximum_step_z=1.0, lag1_acf=0.0, noise_screen_pass=local)))


def tape(*rows):
    return dict(screen="after_salvage", tracks=list(rows))


def test_deferred_only_and_original_rows_are_unchanged():
    original = tape(row(1, 3, 1, closed=True), row(2, 3, 2, slope=3.1))
    before = deepcopy(original)
    result = nominate(original)
    assert result["status"] == "deferred_for_independent_check"
    assert result["deferred"]["peer"]["other_radio"] is True
    assert original == before
    assert not any(row["compatible"] for row in original["tracks"])


def test_profile_failure_needs_exact_active_interval_proof():
    closed, peer = row(1, 3, 1, closed=True), row(1, 1, 2, slope=3.1, profile_noise=False)
    original = tape(closed, peer)
    unrelated = track_key(row(1, 1, 3, slope=3.1, profile_noise=False))
    assert nominate(original, certified_profile_slope={unrelated})["status"] == "unknown_profile_failure"
    result = nominate(original, certified_profile_slope={track_key(peer)})
    assert result["deferred"]["peer"]["other_radio"] is False
    assert result["deferred"]["peer"]["profile_proof"] == "pinned_isolated_gate"


@pytest.mark.parametrize("slope", [3.0, None])
def test_passing_boundary_or_unobserved_slope_cannot_nominate(slope):
    alternate = row(2, 3, 2, slope=slope, profile_noise=False)
    original = tape(row(1, 3, 1, closed=True), alternate)
    assert nominate(original, certified_profile_slope={track_key(alternate)})["status"] == "no_slope_peer"


def test_uncertain_rival_prevents_claiming_a_unique_peer():
    original = tape(row(1, 3, 1, closed=True), row(1, 1, 2, slope=3.1),
                    row(2, 3, 3, slope=3.2, profile_noise=False))
    assert nominate(original)["status"] == "ambiguous_peer"


def test_same_lane_cannot_replace_independent_support():
    original = tape(row(1, 3, 1, closed=True), row(1, 3, 2, slope=3.1))
    assert nominate(original)["status"] == "no_slope_peer"


def test_signed_control_with_no_closure_cannot_nominate():
    original = tape(row(1, 1, 2, slope=3.1), row(2, 3, 1))
    assert nominate(original)["status"] == "no_family_closure"


def test_post_freeze_coverage_distinguishes_wrong_role_and_unowned():
    peer = row(1, 1, 2, slope=3.1)
    a, b, c, d = peer["observation_ids"]
    original = {a: (100, "conditional")}
    named = {a: (100, "conditional"), b: (100, "conditional"), c: (100, "predictive")}
    assert support_coverage([peer], original, named) == dict(matched_missing_installed=1,
        wrong_satellite_or_role=1, extra_relative_to_installed=1, already_owned=1)
