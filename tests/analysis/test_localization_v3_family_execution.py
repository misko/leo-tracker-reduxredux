"""Owned family scheduling preserves the frozen serial policy's science."""

import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import algo07v3_prefamily_policy_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import history_policy as owned
from leo.operations.localization_v3_parallel import ParallelFitFailure, map_initial_arms
from tests.analysis.test_localization_v3_position import prepared


def test_serial_oracle_is_frozen():
    assert hashlib.sha256(Path(oracle.__file__).read_bytes()).hexdigest() == (
        'fa60d1a9d41d0d74e7cb07118423dc2b8ac1467ba809b230317556a6d8dfdda1'
    )


@pytest.mark.parametrize('mapper', [None, map_initial_arms])
@pytest.mark.parametrize('masked', [False, True])
def test_owned_real_curved_fits_match_serial_oracle(mapper, masked):
    scan, node = prepared()
    scan.previous_sources = {}
    scan.elements = {'99999': dict(provenance=dict(element_epoch_utc_ns=0))}
    keep = np.ones(41, bool)
    if masked:
        keep[::3] = False
    arguments = (scan, node, keep, np.ones(1), np.zeros(1), dict(multiplier=1., nu=4.))
    reference = oracle.history_fit(*copy.deepcopy(arguments))
    actual = owned.history_fit(*copy.deepcopy(arguments), map_arms=mapper)
    assert fingerprint(reference) == fingerprint(actual)


@pytest.mark.parametrize('mapper', [None, map_initial_arms])
def test_successive_rejections_are_shared_by_both_arms(monkeypatch, mapper):
    def problem(*args):
        return SimpleNamespace(rows=[dict(component=c) for c in 'abc'],
                               slices=[slice(0, 2), slice(2, 4), slice(4, 6)])

    def refit(scan, node, keep, arm, *args):
        failed = 'a' if keep[0] and arm == 'c0' else (
            'b' if not keep[0] and keep[2] and arm == 'fitted_c' else None)
        tracks = [dict(component=c, compatible=c != failed)
                  for i, c in enumerate('abc') if keep[2 * i]]
        return dict(gates=dict(tracks=tracks), arm=arm, mask=keep.copy())

    for module in (oracle, owned):
        monkeypatch.setattr(module, 'problem', problem)
        monkeypatch.setattr(module, 'refit', refit)
    keep = np.ones(6, bool)
    arguments = (None, None, keep, np.ones(3), np.zeros(3), dict(multiplier=1., nu=4.))
    reference = oracle.history_fit(*arguments)
    actual = owned.history_fit(*arguments, map_arms=mapper)
    assert fingerprint(reference) == fingerprint(actual)
    pair, mask, history = actual
    assert list(pair) == ['c0', 'fitted_c']
    assert history == [dict(epoch=0, input_points=6, failed=['a']),
                       dict(epoch=1, input_points=4, failed=['b']),
                       dict(epoch=2, input_points=2, failed=[])]
    np.testing.assert_array_equal(mask, [False, False, False, False, True, True])
    np.testing.assert_array_equal(keep, np.ones(6, bool))
    for arm in pair.values():
        np.testing.assert_array_equal(arm['mask'], mask)


def test_owned_failed_arm_aborts_instead_of_rejecting_evidence(monkeypatch):
    monkeypatch.setattr(owned, 'problem', lambda *args: None)

    def refit(scan, node, keep, arm, *args):
        if arm == 'fitted_c':
            raise RuntimeError('family worker failed')
        return dict(gates=dict(tracks=[]))

    monkeypatch.setattr(owned, 'refit', refit)
    with pytest.raises(ParallelFitFailure, match='family worker failed'):
        owned.history_fit(None, None, np.ones(1, bool), None, None,
                          dict(multiplier=1., nu=4.), map_arms=map_initial_arms)
