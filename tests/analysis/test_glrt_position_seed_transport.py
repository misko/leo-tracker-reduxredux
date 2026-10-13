import numpy as np
import pytest

from leo.analysis.glrt_position_seed_transport import transport_bias_phase


def test_transport_preserves_curves_under_bias_and_time_shift_and_respects_bounds():
    time = np.linspace(0, 2 * np.pi, 400)
    timing = np.column_stack((500 * np.sin(time), 700 * np.cos(time)))
    reference = np.column_stack((10000 * np.sin(time), -20000 * np.cos(time)))
    displacement = np.array([0.25, -0.4])
    target = reference + np.array([3000, -4000]) + timing * displacement
    phase, bias, rms = transport_bias_phase(
        reference,
        target,
        timing,
        np.ones_like(target),
        [0.2, -0.3],
        [6000, -5000],
        scale_hz=250,
        phase_sigma_s=1,
        bias_sigma_hz=2000,
    )
    np.testing.assert_allclose(phase, [0.2, -0.3] - displacement, atol=0.001)
    np.testing.assert_allclose(bias, [3000, -1000], atol=1)
    assert np.max(rms) < 1
    phase, bias, _ = transport_bias_phase(
        reference,
        target,
        timing,
        np.zeros_like(target),
        [0.2, -0.3],
        [6000, -5000],
        scale_hz=250,
        phase_sigma_s=1,
        bias_sigma_hz=2000,
    )
    np.testing.assert_array_equal(phase, [0.2, -0.3])
    np.testing.assert_array_equal(bias, [6000, -5000])
    phase, bias, _ = transport_bias_phase(
        reference,
        reference + 1e6 + timing * 50,
        timing,
        np.ones_like(target),
        [0, 0],
        [0, 0],
        scale_hz=250,
        phase_sigma_s=1,
        bias_sigma_hz=2000,
    )
    assert np.max(np.abs(phase)) <= 10
    assert np.max(np.abs(bias)) <= 20000
    with pytest.raises(ValueError, match="finite curve"):
        transport_bias_phase(
            reference,
            target,
            timing,
            -np.ones_like(target),
            [0, 0],
            [0, 0],
            scale_hz=250,
            phase_sigma_s=1,
            bias_sigma_hz=2000,
        )
