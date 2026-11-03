import numpy as np
import pytest

from ds23_joint_component_rf import JointComponentWorkspace, common_segments


def workspace(samples=None, per_tone=False):
    rng = np.random.default_rng(413)
    if samples is None:
        samples = rng.normal(size=20000)+1j*rng.normal(size=20000)
    support = [np.arange(a, a+1200) for a in [250, 3650, 7050, 10450, 13850]]
    return JointComponentWorkspace(samples, 2500000., 'lower', [23.2, 193.4], support, per_tone=per_tone)


@pytest.mark.parametrize('per_tone', [False, True])
def test_two_component_projected_gradient_matches_finite_difference(per_tone):
    ws = workspace(per_tone=per_tone)
    parameters = np.array([12000., .133, 6.43, 42000., -.237, -3.29])
    result = ws.statistics(parameters)
    for k in range(6):
        step = [1e-3, 1e-7, 1e-6][k % 3]
        delta = np.zeros(6)
        delta[k] = step
        numeric = (ws.statistics(parameters+delta, derivatives=False)['score']
            - ws.statistics(parameters-delta, derivatives=False)['score'])/(2*step)
        np.testing.assert_allclose(result['gradient_score'][k]/ws.parameter_scale[k],
            numeric, rtol=3e-4, atol=3e-10)


def test_joint_fit_recovers_two_carriers_despite_simultaneous_interference():
    ws = workspace()
    truth = np.array([12000., .123, 6.4, 42000., -.234, -3.3])
    columns = ws.columns(truth)
    y = np.zeros_like(ws.y)
    for k, ix in enumerate(ws.frames):
        y[ix] = columns[ix]@np.array([1+2j, -2+.8j])*np.exp(.3j*k)+(k+1j)
    fitted = workspace(y)
    seeds = [dict(CFO_hz=p[0]-17, offset_samples=p[1]+.02, modulation_ppm=p[2]+.2)
        for p in truth.reshape(2, 3)]
    result = fitted.joint_fit(seeds)
    assert result['score'] > 1-1e-7
    np.testing.assert_allclose(result['parameters'][::3], truth[::3], atol=.1, rtol=0)


def test_common_support_never_reuses_a_transmitter_frame():
    n = np.arange(1000)
    geometries = [dict(valid=np.ones(1000, bool), frame=(n+offset)//100) for offset in [0, 0, 20, 20]]
    selected = common_segments(geometries, minimum_samples=20, trim=2)
    for g in geometries:
        frames = [g['frame'][ix[0]] for ix in selected]
        assert len(frames) == len(set(frames))


@pytest.mark.parametrize('per_tone', [False, True])
def test_joint_objective_cannot_read_held_IQ(per_tone):
    first = workspace(per_tone=per_tone)
    used = np.zeros(len(first.y), bool)
    used[np.concatenate(first.frames)] = True
    changed = first.y.copy()
    changed[~used] += 1e6+2e6j
    second = workspace(changed, per_tone=per_tone)
    p = [12000., .133, 6.43, 42000., -.237, -3.29]
    for key in ['score', 'gradient_score', 'normal', 'rhs', 'raw_energy']:
        np.testing.assert_array_equal(first.statistics(p)[key], second.statistics(p)[key])
