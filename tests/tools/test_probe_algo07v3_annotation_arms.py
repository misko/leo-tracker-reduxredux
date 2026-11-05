import ast

import numpy as np
import probe_algo07v3_annotation_arms as probe
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared


def context():
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=scan.origin_utc_ns))}
    p = NormalPosition(scan, node, 150., False)
    keep = np.ones(len(p.values), bool)
    keep[::3] = False
    return dict(scan=scan, node=node, keep=keep, powers=np.ones(len(p.members)),
                problems={'c0': (p, np.zeros(2))}, means=np.zeros(len(p.labels)),
                model=dict(multiplier=1., nu=4., shrinkage=.5), entries=[])


def test_transform_changes_only_the_training_dictionary():
    _, before, after = probe.transform()
    old, new = ast.parse(before), ast.parse(after)
    for tree in (old, new):
        row = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   and ast.unparse(n.targets[0]) == 'base')
        row.value = ast.Constant(None)
    assert ast.dump(old) == ast.dump(new)


@pytest.mark.parametrize('parallel', [False, True])
def test_reconstructed_both_arm_fits_match_full_training(parallel):
    d = context()
    expected = {a: probe.prediction.fit_training(d, d['node'], d['keep'], a)
                for a in probe.prediction.ARMS}
    mapper = probe.map_initial_arms if parallel else map
    actual = probe.training_pair(d, d['node'], d['keep'], mapper)
    for arm in probe.prediction.ARMS:
        p, x, meta = actual[arm]
        old, old_x, old_meta = expected[arm]
        assert fingerprint((x, meta, p.calculate(x), p.state(x))) == fingerprint(
            (old_x, old_meta, old.calculate(old_x), old.state(old_x)))
        assert len(meta['history']) == 5
        np.testing.assert_array_equal(p.keep, d['keep'])
        np.testing.assert_array_equal(p.point_noise, np.full(len(p.values), 150.))


def test_reconstruction_rejects_changed_reference():
    d = context()
    record = probe.trained_record(d, d['node'], d['keep'], 'c0')
    record['reference'] += .1
    with pytest.raises(ValueError, match='likelihood differs'):
        probe.restore_record(d, d['node'], d['keep'], 'c0', record)


def test_stateful_policy_and_child_failure_cannot_return_science():
    with pytest.raises(ValueError, match='numerical-policy'):
        probe.training_pair(dict(numerical_policy=object()), {}, [], map)

    def fail(operation, items):
        raise RuntimeError('child failed')

    with pytest.raises(RuntimeError, match='child failed'):
        probe.training_pair({}, {}, [], fail)
