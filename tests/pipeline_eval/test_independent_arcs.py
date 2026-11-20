from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import independent_arcs as receiver
from tools.pipeline_eval.variants.peak_paths import Lane


def test_same_pilot_bonus_keeps_unpaired_and_uncalibrated_lanes():
    t = np.array([1.0, 2.0])
    visits = np.array([4, 5])
    marks = np.ones((2, 4))
    y = np.array([[100, 1000, 2000, 3000], [400, 5000, 6000, 7000.0]])
    left = Lane((0, 1, 11.0e9), visits, t, y, marks)
    right = Lane((1, 1, 11.0e9), visits, t, y + 5000, marks)
    uncalibrated = Lane((1, 8, 12.2e9), visits, t, y, marks)
    fused = Lane(left.key, visits, t, y + 4, marks)
    verified = np.zeros_like(y, dtype=bool)
    verified[0, 0] = True
    ids = receiver.corroborate(
        [left, right, uncalibrated],
        [fused],
        [verified],
        {0: dict(offset_hz=5000, drift_hz_per_s=0)},
        duration=100,
    )
    assert [(x >= 0).sum() for x in ids] == [1, 1, 0]
    assert ids[0][0, 0] == ids[1][0, 0] == 0
    np.testing.assert_array_equal(left.y, y)
    np.testing.assert_array_equal(right.y, y + 5000)


def test_joint_factor_uses_one_copy_even_when_two_orbits_claim_a_pair():
    left = SimpleNamespace(key=(0, 3, 11.4e9))
    right = SimpleNamespace(key=(1, 3, 11.4e9))
    visits = np.arange(10)
    ids = np.array([0, 1, -1, -1, -1, -1, -1, -1, -1, -1])
    arc = dict(lane=0, orbit=4, visit=visits, pairs=ids, t=visits.astype(float), y=visits)
    same = dict(arc, lane=1)
    distinct = dict(same, orbit=5)
    result = receiver.unique([arc, same, distinct], [left, right])
    assert [len(a["t"]) for a in result] == [10, 8, 8]
    np.testing.assert_array_equal(result[1]["visit"], visits[2:])


def test_c0_design_omits_calibration_column_and_fitted_arm_estimates_it(monkeypatch):
    bank = SimpleNamespace(duration_s=120, ecef_center_km=np.zeros(3))
    monkeypatch.setattr(receiver.paths, "slice_orbit", lambda bank, _selection: bank)
    monkeypatch.setattr(receiver.paths, "site", lambda _b, xy: (np.r_[xy, 0], [0, 0]))

    def geometry(_bank, t, _phase, _site, _rf):
        return np.zeros(len(t)), np.zeros((len(t), 2))

    monkeypatch.setattr(receiver.paths, "orbit_geometry", geometry)
    measured = []
    scipy_solver = receiver.lsq_linear

    def record(a, b, **kw):
        measured.append(a.shape[1])
        return scipy_solver(a, b, **kw)

    monkeypatch.setattr(receiver, "lsq_linear", record)
    t = np.arange(10, 100, dtype=float)
    rf = (10.8e9, 11.8e9)
    lanes = [Lane((0, j + 1, f), t.astype(int), t, None, None) for j, f in enumerate(rf)]
    arcs = [
        dict(lane=j, orbit=0, phase=0, t=t, y=np.full(len(t), 1200 * (f / 1e9 - 11.5)))
        for j, f in enumerate(rf)
    ]
    c0 = receiver.fit(bank, lanes, arcs, np.zeros(4), 12.5, False)
    assert c0[0][10] == 0 and set(measured) == {11}
    measured.clear()
    fitted = receiver.fit(bank, lanes, arcs, np.zeros(4), 12.5, True)
    assert set(measured) == {12}
    assert abs(fitted[0][10] - 1200) < 5
    assert fitted[2] < c0[2]


def test_left_out_identity_compares_the_same_held_native_visits(monkeypatch):
    bank = SimpleNamespace(duration_s=120)
    monkeypatch.setattr(receiver.paths, "slice_orbit", lambda _bank, selection: selection.start)
    monkeypatch.setattr(receiver.paths, "site", lambda _bank, _xy: (np.zeros(3), [0, 0]))

    def geometry(orb, t, phase, _site, _rf, **_kwargs):
        return np.atleast_2d((120 if orb == 0 else -120) * (t + phase))

    monkeypatch.setattr(receiver.paths, "orbit_geometry", geometry)
    t = np.arange(60, dtype=float)
    y = np.column_stack((120 * t, np.zeros((len(t), 3))))
    marks = np.column_stack((np.full(len(t), 1.45), np.full((len(t), 3), -np.inf)))
    lane = Lane((0, 1, 11.0e9), t.astype(int), t, y, marks)
    train = receiver.paths.blocks(t)[0]
    arc = dict(orbit=0, phase=0, t=t[train], y=y[train, 0])
    rival = dict(orbit=1, phase=0)
    forward = receiver.test_identity(bank, lane, arc, [rival], (np.zeros(11),), 0.0)
    assert forward["held_points"] == 15
    assert forward["picked_score"] > forward["rival_scores"][0]

    held = receiver.paths.blocks(t)[1]
    np.testing.assert_array_equal(arc["t"], t[train])
    y[held, 0] += 5000
    null = receiver.test_identity(bank, lane, arc, [rival], (np.zeros(11),), 0.0)
    assert null["held_points"] == 0
    assert null["picked_score"] == 0
