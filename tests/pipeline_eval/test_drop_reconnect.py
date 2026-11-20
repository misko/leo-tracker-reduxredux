from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.qualification.drop_mechanism_trial import count_match
from tools.pipeline_eval.variants.drop_reconnect import fixed_links

CONFIG = SimpleNamespace(
    max_gap_s=10.0, alias_spacing_hz=1000, association_sigma=3, noise_sigma_hz=10
)


def sample(two_tracks=False):
    def observation(oid, t, cfo, rx=0):
        return dict(
            observation_id=oid,
            time_s=t,
            measured_cfo_hz=cfo,
            receiver=rx + 1,
            native_receiver_id=rx,
            channel=3,
            actual_rf_hz=11e9,
        )

    def track(name, ids, level):
        return dict(
            key=name,
            times=np.array([1.0, 5.0]),
            values=np.array([level, level]),
            observation_ids=ids,
            receiver=1,
            channel=3,
            rf_hz=11e9,
            pieces=[
                dict(
                    start_s=1.0,
                    end_s=5.0,
                    reference_time_s=3.0,
                    time_scale_s=2.0,
                    coefficients_hz=[level],
                ),
            ],
        )

    observed = [
        observation("a", 1, 80),
        observation("b", 5, 80),
        observation("known", 3, 1084),
        observation("far", 6, 80),
        observation("different", 3.1, 80, rx=1),
    ]
    tracks = [track("one", ["a", "b"], 80)]
    if two_tracks:
        observed += [observation("c", 1, 90), observation("d", 5, 90)]
        tracks.append(track("two", ["c", "d"], 90))
    return dict(tracks=tracks, observations=observed, graph_points=2 * len(tracks))


def test_reconnect_uses_native_point_and_its_existing_alias_lane():
    evidence = sample()
    copied = deepcopy(evidence)
    gaps = [dict(receiver=0, channel=3, actual_rf_hz=11e9, time_s=4.0)]
    joined, witness = fixed_links(evidence, gaps, CONFIG, lambda _: True)
    assert witness == [dict(id="known", track="one", residual_hz=4)]
    assert joined["tracks"][0]["observation_ids"] == ["a", "known", "b"]
    np.testing.assert_array_equal(joined["tracks"][0]["values"], [80, 84, 80])
    assert evidence["tracks"][0]["observation_ids"] == copied["tracks"][0]["observation_ids"]
    assert joined["observations"] is evidence["observations"]


def test_reconnect_requires_gap_and_unique_owner_and_retains_curvature_class():
    evidence = sample()
    wrong_lane = [dict(receiver=0, channel=7, actual_rf_hz=11e9, time_s=4.0)]
    right_lane = [dict(receiver=0, channel=3, actual_rf_hz=11e9, time_s=4.0)]
    assert fixed_links(evidence, wrong_lane, CONFIG, lambda _: True)[1] == []
    assert fixed_links(sample(two_tracks=True), right_lane, CONFIG, lambda _: True)[1] == []
    changes = lambda track: len(track["times"]) >= 3  # noqa: E731
    assert fixed_links(evidence, right_lane, CONFIG, changes)[1] == []


def test_count_matched_loss_is_disjoint_and_depends_only_on_visit_numbers():
    valid, observed = set(range(30)), {1, 4, 8, 12}
    independent = count_match("DS", valid, observed)
    assert len(independent) == len(observed)
    assert independent <= valid and independent.isdisjoint(observed)
    assert independent == count_match("DS", set(reversed(sorted(valid))), observed)
