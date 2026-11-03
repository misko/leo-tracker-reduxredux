from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
from ds23_joint_component_refinement import JointComponentWorkspace


def workspace():
    rng = np.random.default_rng(101)
    fs = 2.5e6; n = 50000
    fits = [dict(CFO_hz=12000., offset_samples=.12, modulation_ppm=2.),
            dict(CFO_hz=-28000., offset_samples=-.17, modulation_ppm=-3.)]
    p = JointComponentWorkspace(rng.normal(size=n)+1j*rng.normal(size=n), fs, 'upper', [100., 800.], fits)
    (a, _), (b, _) = [p.columns_and_derivatives(v, k) for k, v in enumerate(p.start.reshape(2, 3))]
    for segment in p.segments:
        # Frame phases reset independently: the estimator must not rely on coherence.
        c = rng.normal(size=17)+1j*rng.normal(size=17)
        p.y[segment] += np.column_stack((a[segment], b[segment], np.ones(len(segment))))@c
    return p


def test_joint_variable_projection_gradient_matches_finite_differences():
    p = workspace(); x = p.start.copy(); x[[0, 3]] += [6., -7.]
    x[[1, 4]] += [.015, .021]; x[[2, 5]] += [.2, -.1]
    analytic = p.statistics(x, 0)['gradient_score']
    finite = []
    for k in range(6):
        delta = np.zeros(6); delta[k] = p.scale[k]*1e-5
        finite.append((p.statistics(x+delta, 0, derivatives=False)['score']-p.statistics(x-delta, 0, derivatives=False)['score'])/2e-5)
    np.testing.assert_allclose(analytic, finite, rtol=2e-4, atol=3e-7)


def test_joint_frequency_fit_improves_training_and_predicts_other_symbols():
    p = workspace(); truth = p.start.copy(); p.start[[0, 3]] += [12., -14.]
    initial = p.statistics(p.start, 0, prediction=True)
    result = p.optimize(0, active=(0, 3), iterations=12)
    final = p.statistics(result['parameters'], 0, prediction=True)
    assert result['score'] > initial['score']
    assert final['heldout_squared_error'] < initial['heldout_squared_error']
    assert np.max(abs(result['parameters'][[0, 3]]-truth[[0, 3]])) < 10
