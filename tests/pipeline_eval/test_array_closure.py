import json

import numpy as np

from tools.pipeline_eval.variants import array_closure as model


def measured(t, doppler, vector, clock):
    f = 100e3 + doppler * t
    phi = np.column_stack((vector.real, vector.imag)) + clock
    tx = np.exp(1j * 72.0 * t)
    iq = np.column_stack((np.exp(1j * phi[:, 1]), np.ones(len(t)), np.exp(-1j * phi[:, 0])))
    return np.column_stack((t, f, tx[:, None] * iq))


def test_exact_cross_satellite_phase_cancels_arbitrary_common_channel_phase():
    t = np.arange(0, 25, 0.05)
    clock = np.column_stack((t * 0.002, 0.4 - t * 0.001))
    a = measured(t, -210, 2.7 + 3j + t * (0.01 + 0.02j), clock)
    b = measured(t, -500, -2.8 - 3j + t * (0.02 - 0.01j), clock)
    seen, rows = model.exact_pairs(model.native_rows(a), model.native_rows(b))
    assert len(t) == seen
    assert len(rows) >= 3
    for row, _, _ in rows.values():
        x = row[..., 2] + 1j * row[..., 3]
        expected = -5.5 - 6j + row[0, :, 0] * (0.01 - 0.03j)
        np.testing.assert_allclose(
            model.wrap(model.phase_difference(x, "closure") - expected), 0, atol=1e-12
        )
    groups, _ = model.support([a, b], set(), (t, clock))
    json.dumps(groups, allow_nan=False)


def test_no_near_timestamp_is_called_exact():
    t = np.arange(0, 18, 0.05)
    clock = np.zeros((len(t), 2))
    a = model.native_rows(measured(t, -210, 0 * t, clock))
    b = model.native_rows(measured(t + 0.01, -310, 0 * t, clock))
    assert model.exact_pairs(a, b) == (0, {})


def test_wire_bridge_requires_full_bracket_and_bounded_reference_changes():
    t = np.array([0, 6, 12, 18, 24.0])
    phases = np.c_[t / 400, -t / 300]
    assert model.wire_stability(t, phases, 1, 19) == 0.08
    assert model.wire_stability(t, phases, -0.2, 19) is None
    assert model.wire_stability(t, phases, 1, 25) is None
    assert model.wire_stability(t[::3], phases[::3], 1, 11) is None
    assert model.wire_stability(t, 3 * phases, 1, 19) is None


def test_chord_score_marginalizes_wrapped_cycles_without_unwrapping():
    v = np.array([1 + 1j, 3.1 - 3.1j])
    q = v + 2 * np.pi * np.array([2 - 4j, -1 + 3j])
    np.testing.assert_allclose(model.wrap_cost(v), model.wrap_cost(q))
    np.testing.assert_allclose(model.wrap(q), v)
