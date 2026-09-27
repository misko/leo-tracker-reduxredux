from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT)]

from bank import MultiTrackBank  # noqa: E402
from tracking import Key, Observation, Policy  # noqa: E402

RATE = 2_500_000
KEY = Key("session", 0, 2, "upper", RATE)


def observation(epoch: float, cfo: float, margin: float = 0.2) -> Observation:
    return Observation(0, epoch, cfo, margin + 0.03, 0.03, True, "fitted", cfo)


def predicted_observation(prediction, margin: float = 0.2) -> Observation:
    return Observation(
        prediction.window,
        prediction.epoch_samples,
        prediction.cfo_hz,
        margin + 0.03,
        0.03,
        True,
        "predicted_verified",
        prediction.scoring_cfo_hz,
    )


def test_capacity_is_three_and_evicts_frozen_weakest_tie() -> None:
    bank = MultiTrackBank(maximum_tracks=3)
    plan = bank.begin(KEY, 1_000_000, 1)
    ids = bank.discover(plan, [
        observation(100, -300_000, 0.1),
        observation(500, -100_000, 0.2),
        observation(900, 100_000, 0.3),
        observation(1300, 300_000, 0.4),
    ])
    assert len(bank.tracks(KEY)) == 3
    assert len(ids) == 3
    assert {track.last_observation.cfo_hz for track in bank.tracks(KEY)} == {
        -100_000,
        100_000,
        300_000,
    }


def test_expiry_removes_every_track_without_copying_detection() -> None:
    bank = MultiTrackBank(Policy(max_age_seconds=2.0))
    first = bank.begin(KEY, 1_000_000, 1)
    bank.discover(first, [observation(100, 20_000)])
    expired = bank.begin(KEY, 1_000_000 + 2 * RATE + 1, 2)
    assert expired.reason == "cold"
    assert expired.tracks == ()
    assert bank.tracks(KEY) == ()


def test_global_periodic_discovery_cannot_be_evaded_by_switching_tracks() -> None:
    bank = MultiTrackBank(Policy(discovery_interval=3), maximum_tracks=3)
    first = bank.begin(KEY, 1_000_000, 1)
    bank.discover(first, [observation(100, -100_000), observation(800, 100_000)])
    second = bank.begin(KEY, 1_100_000, 2)
    one = second.tracks[0]
    selected = bank.accept_cached(second, {
        one.track_id: predicted_observation(one.prediction),
    })
    assert selected.selected_track_id == one.track_id
    third = bank.begin(KEY, 1_200_000, 3)
    other = next(item for item in third.tracks if item.track_id != one.track_id)
    selected = bank.accept_cached(third, {
        other.track_id: predicted_observation(other.prediction),
    })
    assert selected.selected_track_id == other.track_id
    assert bank.accepted_since_discovery(KEY) == 2
    forced = bank.begin(KEY, 1_300_000, 4)
    assert forced.reason == "periodic_discovery"
    assert forced.tracks == ()
    assert len(forced.association_tracks) == 2
    bank.discover(forced, [])
    assert bank.accepted_since_discovery(KEY) == 0
    after_negative_discovery = bank.begin(KEY, 1_400_000, 5)
    assert after_negative_discovery.reason == "predicted_bank"
    assert len(after_negative_discovery.tracks) == 2


def test_negative_and_wrong_cache_checks_do_not_advance_state() -> None:
    bank = MultiTrackBank(maximum_tracks=3)
    first = bank.begin(KEY, 1_000_000, 1)
    bank.discover(first, [observation(100, 50_000)])
    original = bank.tracks(KEY)[0]
    original_start = original.last_start_counter

    second = bank.begin(KEY, 1_100_000, 2)
    item = second.tracks[0]
    negative = Observation(
        item.prediction.window,
        item.prediction.epoch_samples,
        item.prediction.cfo_hz,
        0.04,
        0.03,
        True,
        "predicted_verified",
        item.prediction.scoring_cfo_hz,
    )
    result = bank.accept_cached(second, {item.track_id: negative})
    assert result.observation is None
    assert bank.accepted_since_discovery(KEY) == 0
    assert bank.tracks(KEY)[0].last_start_counter == original_start

    third = bank.begin(KEY, 1_200_000, 3)
    item = third.tracks[0]
    wrong = predicted_observation(item.prediction)
    wrong = Observation(
        wrong.window,
        wrong.epoch_samples,
        wrong.cfo_hz + 20_000,
        wrong.exact,
        wrong.control,
        True,
        wrong.timing_kind,
        wrong.scoring_cfo_hz,
    )
    result = bank.accept_cached(third, {item.track_id: wrong})
    assert result.observation is None
    assert bank.accepted_since_discovery(KEY) == 0
    assert bank.tracks(KEY)[0].last_start_counter == original_start


def test_begin_rejects_replay_or_lookahead_order() -> None:
    bank = MultiTrackBank()
    bank.begin(KEY, 1_000_000, 10)
    with pytest.raises(ValueError):
        bank.begin(KEY, 1_000_000, 11)
    with pytest.raises(ValueError):
        bank.begin(KEY, 1_100_000, 10)


def test_one_plan_cannot_update_twice() -> None:
    bank = MultiTrackBank()
    first = bank.begin(KEY, 1_000_000, 1)
    bank.discover(first, [observation(100, 50_000)])
    with pytest.raises(ValueError):
        bank.discover(first, [observation(200, 60_000)])

    second = bank.begin(KEY, 1_100_000, 2)
    item = second.tracks[0]
    bank.accept_cached(second, {item.track_id: predicted_observation(item.prediction)})
    with pytest.raises(ValueError):
        bank.accept_cached(second, {item.track_id: predicted_observation(item.prediction)})
    with pytest.raises(ValueError):
        bank.discover(second, [])
