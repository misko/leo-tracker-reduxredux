import numpy as np
import pytest
from scipy.linalg import null_space

from ds23_joint_receiver_iq import JointReceiverIQ, conditional_frame_density


SEGMENTS = [np.arange(a, a+1000) for a in [250, 3650, 7050, 10450, 13850, 17250]]
EPOCHS = np.array([[23.2, 193.4], [23.28, 193.35]])


def make(samples=None, separate=False, segments=SEGMENTS):
    if samples is None:
        rng = np.random.default_rng(713)
        samples = rng.normal(size=(2, 20000))+1j*rng.normal(size=(2, 20000))
    return JointReceiverIQ(samples, 2500000., 'lower', EPOCHS, segments, [.01, .015], separate_clocks=separate)


def truth(separate=False):
    return np.r_[12000., 42000., ([1500., 1550.] if separate else [1500.]),
        .123, 6.4, -.234, -3.3, .143, 6.2, -.214, -3.1, .8, .2, .9, -.1]


def synthesize(separate=False):
    base = make(separate=separate)
    p = truth(separate)
    signals = base.signals(p)
    signals[1] *= base.ratios(p)
    y = np.zeros_like(base.y)
    rng = np.random.default_rng(419)
    for k, ix in enumerate(SEGMENTS):
        g = rng.normal(size=2)+1j*rng.normal(size=2)
        for rx in [0, 1]:
            y[rx, ix] = signals[rx][ix]@g+(k+1j*rx)
    return y


@pytest.mark.parametrize('separate', [False, True])
def test_joint_RF_gradient_matches_finite_difference(separate):
    ws = make(separate=separate)
    p = truth(separate)
    p[ws.code_start] += .003
    result = ws.statistics(p)
    for k in range(ws.width):
        delta = np.zeros_like(p)
        step = 1e-3 if k < ws.code_start else (1e-7 if k < ws.ratio_start and (k-ws.code_start) % 2 == 0 else 1e-6)
        delta[k] = step
        finite = (ws.statistics(p+delta, derivatives=False)['quadratic']
            - ws.statistics(p-delta, derivatives=False)['quadratic'])/(2*step)
        np.testing.assert_allclose(result['gradient_quadratic_scaled'][k]/ws.scale[k], finite,
            atol=.002, rtol=3e-4)


def test_joint_RF_recovers_carriers_and_clock_with_arbitrary_frame_TX_phase():
    y = synthesize()
    ws = make(y, segments=SEGMENTS[:4])
    p = truth()
    start = p.copy()
    start[:3] += [-17., 11., -5.]
    start[ws.code_start:ws.ratio_start:2] += .02
    start[ws.code_start+1:ws.ratio_start:2] += .2
    fitted = ws.fit(start, iterations=36)
    assert fitted['score'] > 1-1e-7
    np.testing.assert_allclose(fitted['source_carrier_hz'], p[:2], atol=.2)
    np.testing.assert_allclose(fitted['receiver_clock_hz'], p[2:3], atol=.1)
    best = ws.predict(fitted['parameters'], SEGMENTS[4:])
    wrong = np.array(fitted['parameters'])
    wrong[2] += 60
    other = ws.predict(wrong, SEGMENTS[4:])
    assert other['NLL'] > best['NLL']+100
    covariance = fitted['frequency_covariance']
    assert covariance.shape == (3, 3)
    assert np.linalg.eigvalsh(covariance).min() > 0
    assert abs(covariance[0, 2])+abs(covariance[1, 2]) > 1e-6


def test_held_IQ_perturbation_cannot_change_training_objective():
    first = make(segments=SEGMENTS[:4])
    changed = first.y.copy()
    used = np.zeros(changed.shape[1], bool)
    used[np.concatenate(SEGMENTS[:4])] = True
    changed[:, ~used] += 1e6+2e6j
    second = make(changed, segments=SEGMENTS[:4])
    p = truth()
    for key in ['quadratic', 'normal', 'rhs', 'raw_energy']:
        np.testing.assert_array_equal(first.statistics(p)[key], second.statistics(p)[key])


def test_source_only_prediction_agrees_with_dense_complex_Gaussian_density():
    rng = np.random.default_rng(871)
    source_basis = rng.normal(size=(18, 2))+1j*rng.normal(size=(18, 2))
    target_basis = rng.normal(size=(21, 2))+1j*rng.normal(size=(21, 2))
    source = rng.normal(size=18)+1j*rng.normal(size=18)
    target = rng.normal(size=21)+1j*rng.normal(size=21)
    actual = conditional_frame_density(source, target, source_basis, target_basis, .3, .5)
    x = np.column_stack((source_basis, np.ones(18)))
    c = np.linalg.lstsq(x, source, rcond=None)[0]
    cov = .3*np.linalg.inv(x.conj().T@x)[:2, :2]
    q = null_space(np.ones((1, 21)))
    e = q.conj().T@(target-target_basis@c[:2])
    covariance = q.conj().T@(.5*np.eye(21)+target_basis@cov@target_basis.conj().T)@q
    nll = float(np.vdot(e, np.linalg.solve(covariance, e)).real+np.linalg.slogdet(covariance)[1]+20*np.log(np.pi))
    np.testing.assert_allclose(actual['NLL'], nll, atol=1e-9)


def test_training_overlap_in_prediction_is_explicitly_rejected():
    with pytest.raises(ValueError, match='overlaps'):
        make().predict(truth(), SEGMENTS[:1])


def test_common_clock_does_not_explain_injected_component_clock_disagreement():
    y = synthesize(separate=True)
    free = make(y, separate=True, segments=SEGMENTS[:4])
    common = make(y, segments=SEGMENTS[:4])
    separate_fit = free.fit(truth(True), iterations=30)
    start = truth()
    start[2] = 1525.
    common_fit = common.fit(start, iterations=30)
    free_held = free.predict(separate_fit['parameters'], SEGMENTS[4:])['NLL']
    common_held = common.predict(common_fit['parameters'], SEGMENTS[4:])['NLL']
    assert common_held-free_held > 100
