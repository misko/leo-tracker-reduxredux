import numpy as np

from tools.pipeline_eval.variants import bearing_transfer as model


def test_measured_fft_cross_phase_changes_cancel_transmitter_and_static_receiver_offsets():
    t = np.arange(0.01, 16, 0.019)
    original = np.stack((t, (-210 + 1000j).real * t), axis=1)
    tx = np.exp(1j * (80 * t + t**2))
    local = np.exp(1j * np.array([0.4, 0.8, 5.6]))
    rates = [0.29, 0.17, 0.02]
    fft = tx[:, None] * local * np.exp(1j * t[:, None] * rates)
    raw = np.column_stack((original, fft))
    duplicated_weak = np.column_stack((original, -0.1 * fft))
    native = np.concatenate((duplicated_weak[::-1], raw))
    a = np.asarray(model.secants(native))
    dt = a[:, 1] - a[:, 0]
    np.testing.assert_allclose(a[:, 2], -210, atol=1.5)
    np.testing.assert_allclose(a[:, 3], dt * (rates[1] - rates[2]), atol=1e-12)
    np.testing.assert_allclose(a[:, 4], dt * (rates[0] - rates[1]), atol=1e-12)
    assert len(a) == 2


def test_global_rotation_and_full_phase_reversal_have_equivalent_free_yaw():
    observed = np.array([1 + 2j, 2 - 3j])
    rotation = np.exp(1.3j)
    modeled = observed / rotation
    freq = np.array([0.0])
    p = np.array([2 * np.mean(abs(observed) ** 2)])
    c = np.array([np.mean(observed * modeled.conj())])
    candidates, estimated = model.discrete_choice([(freq, p, c)], joint=True)
    flipped_candidates, inverted = model.discrete_choice([(freq, p, -c)], joint=True)
    assert candidates == flipped_candidates == [0]
    np.testing.assert_allclose(estimated, rotation)
    np.testing.assert_allclose(inverted, -rotation)


def test_joint_selection_has_one_orientation_across_tracks():
    y = np.array([1 + 2j, 2 - 3j])
    wanted = np.exp(2.1j)
    phase = np.stack((y * -1j, y / wanted), axis=1)
    mirrored = phase.copy()
    mirrored[1, 0] *= -1
    groups = [
        (np.array([0.0, 0.0]), abs(o) ** 2 + abs(p) ** 2, o * p.conj())
        for o, p in zip(y, mirrored, strict=True)
    ]
    indices, yaw = model.discrete_choice(groups, joint=True)
    assert indices == [1, 1]
    np.testing.assert_allclose(yaw, wanted)
    assert model.rms([2, 2j]) == 2
