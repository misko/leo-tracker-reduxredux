from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import derivative_receiver as receiver


def test_cubic_derivative_operator_removes_both_oscillator_terms():
    t = np.linspace(-9.5, 9.5, 18)
    _, derivative, normalized = receiver.polynomial(t)
    y = 3 * t**2 + 0.4 * t**3
    expected_curvature = 6 + 2.4 * np.array([-4.75, 4.75])
    np.testing.assert_allclose(
        derivative @ (y + 180_000 + 1230 * t), expected_curvature, atol=1e-11
    )
    np.testing.assert_allclose(normalized @ (y + 180_000 + 1230 * t), normalized @ y, atol=1e-9)
    np.testing.assert_allclose(normalized @ normalized.T, np.eye(2), atol=1e-14)


def make_arc(y, *, channel=4, rf=11e9):
    t = np.arange(36, dtype=float)
    return receiver.features(dict(times=t, values=y, receiver=0, channel=channel, rf_hz=rf))


def test_coincident_differential_slope_cancels_a_shared_oscillator():
    t = np.arange(36.0)
    first, second = 10 * t**2, 7 * t**2 + 52 * t

    def rates(a, b):
        x = [SimpleNamespace(arc=x) for x in (a, b)]
        return receiver.coincident(x)

    stable, count = rates(make_arc(first), make_arc(second))
    assert count == 1 and len(stable) == 1
    oscillator = 42000 + 878 * t
    common, _ = rates(make_arc(first + oscillator), make_arc(second + oscillator))
    np.testing.assert_allclose(stable[0][4], common[0][4], atol=1e-10)
    assert rates(make_arc(first), make_arc(second, rf=11.0001e9)) == ([], 0)
    separate_carrier, count = rates(make_arc(first), make_arc(second + 9000))
    assert count == 1
    np.testing.assert_allclose(stable[0][4], separate_carrier[0][4], atol=1e-10)


def test_phase_absorbs_an_axis_response_even_for_large_raw_cfo_change():
    t = np.arange(36.0)
    a = make_arc(35 * t**2 + 0.5 * t**3)
    shape = np.stack((2 * t**2, 0.5 * t**3))
    xy = np.array([[-12.5, 0], [12.5, 0], [0, -12.5], [0, 12.5]])
    f = (
        np.einsum("ij,jt->it", xy, shape)[:, None, None]
        + receiver.PHASE[None, None, :, None] * shape[0]
    )
    result = SimpleNamespace(frequency=f, arc=a)
    raw, _, projected = receiver.sensitivity(result, 0, 3, a.head, a.tail, [0, 1, 2, 3])
    assert min(raw) > 1000
    assert np.linalg.norm(projected[0]) < 1e-12
    assert np.linalg.norm(projected[1]) > 0.1


def test_relative_slope_can_change_both_marginal_orbit_winners():
    t = np.arange(36.0)
    a, b = make_arc(20 * t), make_arc(-120 * t)

    def part(arc, numbers, rate):
        f = np.array(rate)[None, :, None, None] * t
        return SimpleNamespace(
            arc=arc,
            norads=np.array(numbers),
            evidence=np.array([[-0.4, 0.0]]),
            phase=np.zeros((1, 2), dtype=int),
            frequency=f,
        )

    shapes = [part(a, [101, 201], [20, -300]), part(b, [102, 202], [-120, 250])]
    pairs, _ = receiver.coincident(shapes)
    independent, _ = receiver.select(shapes, [])
    differential, _ = receiver.select(shapes, pairs)
    assert independent[:, 0].tolist() == [1, 1]
    assert differential[:, 0].tolist() == [0, 0]


def test_no_sufficient_polynomial_support_withholds_both_matched_arms():
    r = receiver.infer(None, [], {"center": [0, 0]}, measured=True)
    assert r["status"] == "withheld" and r["reason"] == "insufficient_derivative_arcs"
    c0, fitted = r["arms"].values()
    assert c0["latlon"] is None and fitted["latlon"] is None
    assert c0["forced_latlon"] is None and fitted["forced_latlon"] is None
    assert c0["c_hz_per_ghz"] == 0 and fitted["c_hz_per_ghz"] is None
