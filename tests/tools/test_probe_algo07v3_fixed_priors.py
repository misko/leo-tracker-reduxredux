"""Fixed-prior fast path must preserve complete output and the general learned path."""

import ast
import hashlib
from pathlib import Path

import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_fixed_priors import candidate, hierarchical


def test_native_overlay_is_measured_prototype_and_reference_is_unchanged():
    assert hashlib.sha256(Path(hierarchical.__file__).read_bytes()).hexdigest() == (
        'c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e')
    report = Path(__file__).resolve().parents[2]/'reports/2026_11_06_algo07v3_fixed_priors'
    path = report/'candidate-src/leo/analysis/localization_v3/hierarchical.py'
    body = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n,ast.FunctionDef) and n.name=='hierarchical_bound')
    assert ast.dump(body) == ast.dump(ast.parse(candidate()[2]).body[0])


@pytest.mark.parametrize('width', [0, 1, 7, 20])
@pytest.mark.parametrize('kind', ['none', 'fixed', 'mixed', 'learned'])
@pytest.mark.parametrize('layout', ['C', 'F'])
def test_complete_result_and_inputs_exact(width, kind, layout):
    rng = np.random.default_rng(671)
    y = rng.normal(size=70)
    x = np.array(rng.normal(size=(70, width)), order=layout)
    x[rng.random(x.shape) < .6] = 0
    sigma, groups = rng.uniform(.8, 3, 70), np.arange(70)%6
    prior = None if kind == 'none' else np.full(width, -1, dtype=int)
    if kind in ('mixed', 'learned'):
        prior[::2 if kind == 'mixed' else 1] = np.arange(width)[::2 if kind == 'mixed' else 1]%3
    args = (y, x, sigma, groups)
    kwargs = dict(prior_groups=prior, powers=np.linspace(.5, 1, 6), iterations=31)
    before = fingerprint((args, kwargs))
    reference = hierarchical.hierarchical_bound(*args, **kwargs)
    actual = candidate()[0](*args, **kwargs)
    assert fingerprint(actual) == fingerprint(reference)
    assert fingerprint((args, kwargs)) == before
    assert not np.shares_memory(actual['coefficient_prior_precision'], x)


@pytest.mark.parametrize('kwargs', [dict(iterations=0), dict(prior_groups=[-2]),
                                   dict(prior_groups=[0, 1]), dict(noise_nu=0)])
def test_invalid_inputs_retain_validation(kwargs):
    args = ([1., 2.], np.ones((2, 1)), [1., 1.], np.array([0, 0]))
    for function in (hierarchical.hierarchical_bound, candidate()[0]):
        with pytest.raises(ValueError):
            function(*args, **kwargs)


@pytest.mark.parametrize('value', [0., -0., 1e-200])
def test_degenerate_calls_keep_bytes_and_do_not_share_precision(value):
    operation = candidate()[0]
    args = (np.full(30, value), np.zeros((30, 5)), 150., np.arange(30)%3)
    first, second = operation(*args), operation(*args)
    assert fingerprint(first) == fingerprint(hierarchical.hierarchical_bound(*args))
    first['coefficient_prior_precision'][0] = 9.
    assert second['coefficient_prior_precision'][0] == 1.


@pytest.mark.parametrize('arm', ['c0', 'fitted_c'])
def test_full_training_history_preserved(arm):
    from benchmark_algo07v3_training_kernel import trial

    from tests.analysis.test_localization_v3_training_records import context
    first, second = context(4.), context(4.)
    baseline = trial(first, first['keep'], arm, hierarchical.hierarchical_bound)
    actual = trial(second, second['keep'], arm, candidate()[0])
    assert actual['signature'] == baseline['signature']


@pytest.mark.parametrize('learned', [False, True])
def test_every_noise_and_prior_transition_remains_exact(learned):
    from profile_algo07v3_precision_trajectory import Trajectory
    _, original, changed = candidate()
    rng = np.random.default_rng(123)
    args = (rng.normal(size=40), rng.normal(size=(40, 8)), 1., np.arange(40)%4)
    kwargs = dict(prior_groups=np.arange(8)%3 if learned else None, iterations=20)
    traces = []
    for source in (original, changed):
        trace = Trajectory()
        needle = '        rate, prior_rate = next_rate, next_prior_rate'
        assert source.count(needle) == 1
        source = source.replace(needle,
            '        _record(rate, prior_rate, next_rate, next_prior_rate, change)\n' + needle)
        scope = dict(vars(hierarchical), _record=trace.record)
        exec(compile(source, '<test-fixed-prior-transitions>', 'exec'), scope)
        scope['hierarchical_bound'](*args, **kwargs)
        traces.append(trace.rows)
    assert fingerprint(traces[0]) == fingerprint(traces[1])
