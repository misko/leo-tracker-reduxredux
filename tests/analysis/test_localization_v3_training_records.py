"""Final-problem recipes preserve full likelihoods and five-round fit metadata."""
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import prediction
from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared


def context(nu):
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=scan.origin_utc_ns))}
    p = NormalPosition(scan, node, 150., False)
    keep = np.ones(len(p.values), bool)
    keep[::3] = False
    return dict(scan=scan, node=node, keep=keep, powers=np.full(len(p.members), .5),
                problems={'c0': (p, np.zeros(2))}, means=np.zeros(len(p.labels)),
                model=dict(multiplier=1., nu=nu, shrinkage=.5), entries=[])


@pytest.mark.parametrize('nu', [None, 4.])
@pytest.mark.parametrize('arm', prediction.ARMS)
def test_training_recipe_reconstructs_every_calculation_and_state(nu, arm):
    d = context(nu)
    old, old_x, old_meta = prediction.fit_training(d, d['node'], d['keep'], arm)
    record = prediction.training_record(d, d['keep'], arm)
    p, x, meta = prediction.restore_training(d, d['keep'], arm, record)
    assert fingerprint((x, meta, p.calculate(x), p.state(x))) == fingerprint(
        (old_x, old_meta, old.calculate(old_x), old.state(old_x)))
    assert len(meta['history']) == 5
    np.testing.assert_array_equal(p.point_noise, np.full(len(p.values), 150.))
    # Returned metadata and fitted coordinates must not alias the portable record.
    meta['history'][0]['endpoint'][0] += 1
    x[0] += 1
    assert fingerprint(record['metadata']) == fingerprint(old_meta)
    np.testing.assert_array_equal(record['endpoint'], old_x)


@pytest.mark.parametrize('change', ['arm', 'mask', 'reference', 'objective'])
def test_changed_recipe_is_rejected(change):
    d = context(4.)
    r = prediction.training_record(d, d['keep'], 'c0')
    if change == 'arm':
        r['arm'] = 'fitted_c'
    elif change == 'mask':
        r['keep'][0] = not r['keep'][0]
    elif change == 'reference':
        r['reference'] += .1
    else:
        r['metadata']['training_objective'] += 1
    with pytest.raises(ValueError):
        prediction.restore_training(d, d['keep'], 'c0', r)


def test_mutable_numerical_training_cannot_be_detached():
    with pytest.raises(ValueError, match='original serial'):
        prediction.training_record({'numerical_policy': object()}, [], 'c0')
