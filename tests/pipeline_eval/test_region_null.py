import numpy as np

from tools.pipeline_eval.variants import region_null as gate


def test_arcs_discard_arbitrary_per_track_offsets():
    tracks = [
        dict(times=np.linspace(i, i + 40, 12), values=np.arange(12) ** 2, rf_hz=11e9)
        for i in (0, 45, 90, 135)
    ]
    plain = gate.arcs(dict(tracks=tracks))
    shifted = gate.arcs(
        dict(
            tracks=[
                dict(row, values=row["values"] + (i + 1) * 24250) for i, row in enumerate(tracks)
            ]
        )
    )
    assert len(plain) == 4
    for lhs, rhs in zip(plain, shifted, strict=True):
        np.testing.assert_array_equal(lhs.centered_hz, rhs.centered_hz)
        np.testing.assert_array_equal(lhs.relative_times, rhs.relative_times)


def test_permutations_preserve_independent_rf_lanes_without_duplicates():
    arcs = [
        gate.Arc(rf, i * 30.0, np.zeros(8), np.ones(8)) for rf in (11e9, 12e9) for i in range(4)
    ]
    plans = gate.schedules(arcs)
    assert plans[0] == tuple(range(8))
    assert len(set(plans)) == 20
    assert plans == gate.schedules(arcs)
    for row in plans:
        assert sorted(row) == list(range(8))
        assert all(arcs[i].rf == arcs[j].rf for i, j in enumerate(row))
    assert len(gate.schedules(arcs[:2])) == 2


def test_null_rank_independent_count_and_geographic_margin_all_required():
    xy = gate.nodes(12.5)
    assert (np.abs(xy[:36]) < 12.5).all()
    assert (np.abs(xy[36:]).max(axis=1) > 12.5).all()
    data = np.array([5.0] * 36 + [3.0] * 36)
    counts = np.array([5] * 72)
    null = np.array([4.0] * 19)
    assert gate.summarize(data, counts, null, xy)["state"] == "inside"
    assert gate.summarize(data[::-1], counts, null, xy)["state"] == "outside"
    assert (
        gate.summarize(data - np.repeat([1.5, 0.0], 36), counts, null * 0.5, xy)["state"]
        == "ambiguous"
    )
    assert gate.summarize(data, counts, [*null[:-1], 5], xy)["null_rank"] == 0.1
    assert gate.summarize(data, counts, [*null[:-1], 5], xy)["state"] == "null_not_separated"
    assert gate.summarize(data, counts - 2, null, xy)["state"] == "null_not_separated"


def test_gate_withholds_without_changing_both_fits_and_does_not_rescue():
    c0 = dict(latlon=[20.0, 1.0], forced_latlon=[20.0, 1.0], c_hz_per_ghz=0.0, rf_rms_hz=150.0)
    fitted = dict(c0, c_hz_per_ghz=22.0, rf_rms_hz=146.0)
    original = dict(status="ok", arms=dict(c0=c0, fitted=fitted))
    filtered = gate.apply(original, {"state": "outside"})
    assert filtered["status"] == "withheld"
    assert filtered["arms"]["c0"]["latlon"] is None
    assert filtered["arms"]["fitted"]["rf_rms_hz"] == 146.0
    assert filtered["arms"]["fitted"]["forced_latlon"] == original["arms"]["fitted"]["latlon"]
    assert gate.apply(filtered, {"state": "inside"})["status"] == "withheld"
    assert gate.apply(original, {"state": "inside"})["arms"] == original["arms"]


def test_nomination_uses_differential_range_rate_and_horizon(monkeypatch):
    t = np.linspace(-20.0, 20.0, 8)
    site = np.array([[6371.0, 0.0, 0.0]])
    p = np.stack(
        [
            np.column_stack((np.full(8, x), 7.5 * t, np.full(8, 250.0)))
            for x in (6800.0, 4200.0, 7800.0)
        ]
    )
    v = np.tile([0.0, 7.5, 0.0], (3, 8, 1))
    a = np.zeros_like(v)
    relative = p[0] - site
    rf = 11e9
    curve = (
        -rf
        / gate.lean.grid.LIGHT_SPEED_KM_S
        * ((relative * v[0]).sum(axis=-1) / np.linalg.norm(relative, axis=-1))
    )
    row = gate.Arc(rf, 100.0, t, curve - curve.mean())

    def states(tile, requested):
        np.testing.assert_allclose(requested, 100.0 + gate.PAD_S + t, atol=1e-12, rtol=0)
        return p, v, a

    monkeypatch.setattr(gate.lean.grid, "_interpolated_states", states)
    winner, merit = gate.nominate(row, 100.0, None, site)
    np.testing.assert_array_equal(winner, [0])
    np.testing.assert_allclose(merit, [1.0], atol=1e-12)

    monkeypatch.setattr(gate.lean.grid, "_interpolated_states", lambda *_: (p[1:2], v[1:2], a[1:2]))
    _, below_horizon = gate.nominate(row, 100.0, None, site)
    np.testing.assert_array_equal(below_horizon, [0.0])
