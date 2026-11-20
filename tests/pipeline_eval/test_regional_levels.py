from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification.native_joint_full_results import roi_margin
from tools.pipeline_eval.qualification.regional_levels_results import independent_identity
from tools.pipeline_eval.scoring import distance_km
from tools.pipeline_eval.variants import regional_levels as receiver


def test_equal_probe_lattices_keep_all_primary_samples_inside_the_actual_offer():
    offer = {"center": [39.21, -103.6]}
    cells = receiver.cells(offer)
    assert cells == receiver.cells(offer | {"width_km": 25.0})
    assert set(cells) == {"inside", "east", "west", "north", "south"}
    assert len({tuple(p) for rows in cells.values() for p in rows}) == 125
    assert distance_km(cells["inside"][12], offer["center"]) < 1e-6
    assert all(roi_margin(p, offer) >= 0 for p in cells["inside"])
    for name, points in cells.items():
        if name != "inside":
            assert distance_km(points[12], offer["center"]) == pytest.approx(50.0, rel=0.006)
            assert all(roi_margin(p, offer) < 0 for p in points)
    with pytest.raises(ValueError, match="25 km"):
        receiver.cells(offer | {"width_km": 40})


def test_calibration_profiles_freeze_aliases_and_use_held_points_only_for_scoring(monkeypatch):
    points = receiver.cells({"center": [33.1, -101.4]})["inside"]
    arcs = [
        SimpleNamespace(
            time=np.arange(11),
            frequency=np.arange(11, dtype=float),
            train=6,
            group=i // 2,
            channel=i + 1,
            rf=(11.2 + 0.10 * i) * 1e9,
        )
        for i in range(3)
    ]

    def fake_exact(_, tracks, point, __):
        y = np.concatenate([a.frequency for a in tracks])
        f = np.tile(np.arange(11) * (1 + 0.15 * (point[0] - 33.1)), len(tracks))
        use = np.tile(np.arange(11) < 6, len(tracks))
        return (
            f,
            y,
            use,
            np.repeat([a.group for a in tracks], 11),
            np.repeat([a.rf for a in tracks], 11),
        )

    monkeypatch.setattr(receiver.world, "exact", fake_exact)
    row = SimpleNamespace(
        point=points[12],
        assignments=([(i, 0.0, 0.0) for i in range(3)], []),
        levels=([0.0] * 4, []),
    )
    before = receiver.profile(None, [1, 2, 3], arcs, row, 0, points)
    arcs[0].frequency[6:] += 500
    after = receiver.profile(None, [1, 2, 3], arcs, row, 0, points)
    assert before["aliases"] == after["aliases"]
    for arm in ("c0", "fitted_c"):
        a, b = before["best"][arm], after["best"][arm]
        assert a["point"] == b["point"]
        assert a["rf_rms_hz"] == b["rf_rms_hz"]
        assert b["held_rms_hz"] > a["held_rms_hz"] + 100


def test_identity_comparison_rejects_alias_ambiguity_and_counts_exact_common_peaks():
    trace = [
        dict(
            receiver=0, channel=1, rf_hz=11e9, norad=16, held_start=0, time_s=[4, 5], cfo_hz=[9, 11]
        )
    ]
    first, second = (0, 1, 11e9, 4), (0, 1, 11e9, 5)
    archived = {
        first: {"norad": 16, "candidate_rank": 1},
        second: {"norad": 16, "candidate_rank": 1},
    }
    samples = {
        first: [{"fractional_tracking_cfo_hz": 9, "candidate_rank": 1}],
        second: [
            {"fractional_tracking_cfo_hz": 11, "candidate_rank": 1},
            {
                "fractional_tracking_cfo_hz": 11 + receiver.world.physical.PERIOD_HZ,
                "candidate_rank": 2,
            },
        ],
    }
    result = independent_identity(trace, samples, archived=archived)
    assert result == dict(
        identity_compared_points=1,
        identity_agree_points=1,
        identity_agree_orbits=1,
        identity_ambiguous_cfo_rows=1,
    )
