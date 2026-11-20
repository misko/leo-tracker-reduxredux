from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import orbit_continuity as model


def test_coherence_rejects_sparse_frequency_coincidences():
    t = np.arange(19.0)
    residual = np.zeros(len(t))
    assert len(model.coherent(t, residual)) == len(t)
    residual[1::2] = 3500
    assert len(model.coherent(t, residual)) == len(t[::2])
    residual[2::4] = 3500
    assert not len(model.coherent(t, residual))


def test_prediction_keeps_early_level_exact_carrier_and_orbit():
    N, rf = 15, 11.5e9
    t = np.arange(20.0, 20.0 + N)
    knots = np.arange(0.0, 70.0, 5.0)
    p = np.column_stack((np.full(len(knots), 6900.0), 4 * knots, np.zeros(len(knots))))
    v = np.broadcast_to([0.0, 4.0, 0.0], p.shape)
    states = model.grid.Tile(np.zeros(3), np.eye(3), 60.0, knots, p[None], v[None], {})
    actual = np.column_stack((np.full(N, 6900.0 - 6378.137), 4 * t, np.zeros(N)))
    rate = actual @ np.array([0.0, 4.0, 0.0]) / np.linalg.norm(actual, axis=1)
    offset = 42000.0
    f = model.native.fold(offset - rf * rate / model.grid.LIGHT_SPEED_KM_S)
    lane = model.native.Lane((0, 1, rf), np.arange(N), t, f[:, None], np.ones((N, 1)))
    link = model.Link(0, 0, 0, rf, 10.0, offset, 0.0)
    found = model.forecast({(0, rf): [lane]}, states, (0.0, 0.0), [link], np.zeros(4), 0)
    absent = model.forecast({(1, rf): [lane]}, states, (0.0, 0.0), [link], np.zeros(4), 0)
    wrong = model.forecast(
        {(0, rf): [lane]},
        states,
        (0.0, 0.0),
        [model.replace(link, intercept_hz=offset + 12000)],
        np.zeros(4),
        0,
    )
    assert found["held_coherent_hits"] == N and found["held_cfo_rms_hz"] < 1e-6
    assert found["held_placebo_hits"] == 0 and found["held_orbits"] == 1
    assert absent["held_visit_opportunities"] == 0 and wrong["held_coherent_hits"] == 0
    assert wrong["held_placebo_hits"] == N and wrong["held_strength"] == -1


def test_shape_ambiguity_prevents_binding_an_early_orbit():
    t = np.arange(12.0)
    arc = SimpleNamespace(group=0, rf=11.5e9, t=t, f=8000 + 40 * t, noise=np.array([30, 4]))
    spectra = [(np.array([0, 1]), np.vstack((40 * t, 40 * t)), np.array([[0, 0], [0, 0.1]]))]
    assert model.winner_links(spectra, [arc], np.zeros(4), 0) == []
    spectra[0][2][1, 1] = 12
    (link,) = model.winner_links(spectra, [arc], np.zeros(4), 0)
    assert link.orbit == 0 and link.intercept_hz == 8000
