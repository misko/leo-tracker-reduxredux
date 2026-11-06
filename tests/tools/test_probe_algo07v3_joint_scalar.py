import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_joint_scalar import candidate

from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from tests.analysis.test_joint_predictive_families import fixture


@pytest.mark.parametrize('mode', [True, False])
@pytest.mark.parametrize('chunk', [1, 6, 32768])
@pytest.mark.parametrize('visibility', ['original', 'none', 'one_family'])
def test_scalar_score_preserves_exact_arithmetic_and_inputs(mode, chunk, visibility):
    fn, _ = candidate()
    args = fixture()
    if visibility != 'original':
        args[-1][0][:] = False
        if visibility == 'none':
            args[-1][1][:] = False
    before = fingerprint(args)
    expected = two_family_phase_evidence(*args, max_pairs=chunk, optimize_contractions=mode)
    actual = fn(*args, max_pairs=chunk, optimize_contractions=mode)
    assert fingerprint(actual) == fingerprint(expected['negative_twice_log_density'])
    assert fingerprint(args) == before


@pytest.mark.parametrize('fault', ['chunk', 'covariance', 'prior'])
def test_scalar_route_keeps_validation_errors(fault):
    fn, _ = candidate()
    args, kwargs = fixture(), {}
    if fault == 'chunk':
        kwargs['max_pairs'] = 0
    elif fault == 'covariance':
        args[2][0, 0] = -100.
    else:
        args[4][0][:] = np.nan
    for operation in (two_family_phase_evidence, fn):
        with pytest.raises((ValueError, np.linalg.LinAlgError)):
            operation(*args, **kwargs)


def test_source_drift_requires_review():
    with pytest.raises(ValueError, match='boundaries'):
        candidate('def changed():\n    return 0\n')
