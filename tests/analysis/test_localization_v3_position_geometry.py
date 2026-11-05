"""Exact fixed-phase cache regression against the frozen original calculator."""

import copy
import hashlib
from pathlib import Path

import algo07v3_preposition_geometry_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import marginal
from leo.analysis.localization_v3.position import NormalPosition
from leo.analysis.localization_v3.region import SearchRegion
from tests.analysis.test_localization_v3_position import prepared


@pytest.fixture(scope='module')
def original():
    assert hashlib.sha256(Path(oracle.__file__).read_bytes()).hexdigest() == (
        '38535668aa81bb2116250225c457721b91a77fbd81084e8675a109ad3aa21c3f')
    return oracle.JointMarginal.calculate


@pytest.mark.parametrize('fitted_c', [False, True])
@pytest.mark.parametrize('geometry_only', [False, True])
@pytest.mark.parametrize('empirical', [False, True])
def test_complete_fields_match_after_reference_and_bank_changes(
        original, fitted_c, geometry_only, empirical):
    scan, node = prepared()
    p = NormalPosition(scan, node, 150., fitted_c)
    if empirical:
        p.variant = 'empirical'
    for change in ('none', 'reference', 'times', 'labels', 'mode_buffer',
                   'sky_buffer', 'copy', 'region', 'prior'):
        if change == 'reference':
            p.reference += 0.25
        elif change == 'times':
            p.flat_times = p.flat_times + 0.01
        elif change == 'labels':
            p.flat_labels = p.flat_labels.astype(np.int32)
        elif change == 'mode_buffer':
            p.mode_bank = dict(p.mode_bank, velocity_km_s=p.mode_bank['velocity_km_s'] + 0.001)
        elif change == 'sky_buffer':
            p.sky = dict(p.sky, position_km=p.sky['position_km'] + 0.01)
        elif change == 'copy':
            p = copy.copy(p)
            p.reference = p.reference - 0.1
        elif change == 'region':
            p.scan = copy.copy(p.scan)
            p.scan.search_region = SearchRegion((5., 20.))
        elif change == 'prior':
            p.phase_sigma = p.phase_sigma * 0.9
        inputs = fingerprint((p.sky, p.mode_bank, p.flat_times, p.flat_labels, p.reference))
        for xy in ([0., 0.], [2., -3.], [-11., 12.]):
            x = xy + ([0.1, -0.2, 0.3] if empirical else [])
            expected = original(p, x, geometry_only=geometry_only)
            actual = marginal.JointMarginal.calculate(p, x, geometry_only=geometry_only)
            assert fingerprint(actual) == fingerprint(expected)
        assert fingerprint((p.sky, p.mode_bank, p.flat_times, p.flat_labels, p.reference)) == inputs


def test_reuse_read_only_snapshots_and_invalid_reference(monkeypatch):
    scan, node = prepared()
    p = NormalPosition(scan, node, 150., False)
    original = marginal.prepare_phase_geometry
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(marginal, 'prepare_phase_geometry', counted)
    for x in ([0, 0], [1, 2], [3, 4]):
        marginal.JointMarginal.calculate(p, x, geometry_only=True)
    assert len(calls) == 1
    with pytest.raises(ValueError, match='read-only'):
        p._fixed_phase_geometry_cache[3][0][0][0, 0] = 99
    p.reference += 0.25
    marginal.JointMarginal.calculate(p, [0, 0], geometry_only=True)
    assert len(calls) == 2
    p.reference += 1e6
    with pytest.raises(ValueError, match='extrapolat'):
        marginal.JointMarginal.calculate(p, [0, 0], geometry_only=True)
