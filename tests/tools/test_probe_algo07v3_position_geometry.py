import copy

import numpy as np
import probe_algo07v3_position_geometry as probe
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3.marginal import JointMarginal
from leo.analysis.localization_v3.position import NormalPosition
from tests.analysis.test_localization_v3_position import prepared


@pytest.mark.parametrize('fitted_c', [False, True])
@pytest.mark.parametrize('geometry_only', [False, True])
def test_complete_calculation_matches_with_phase_and_buffer_changes(fitted_c, geometry_only):
    scan, node = prepared()
    p = NormalPosition(scan, node, 150., fitted_c)
    candidate, _, _ = probe.candidate_function()
    for change in ('none', 'reference', 'times', 'labels', 'mode_buffer', 'sky_buffer', 'copy'):
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
        for x in ([0., 0.], [2., -3.], [-11., 12.]):
            expected = JointMarginal.calculate(p, x, geometry_only=geometry_only)
            actual = candidate(p, x, geometry_only=geometry_only)
            assert fingerprint(actual) == fingerprint(expected)


def test_fixed_problem_reuses_preparation_and_invalid_phase_still_raises(monkeypatch):
    scan, node = prepared()
    p = NormalPosition(scan, node, 150., False)
    original = probe.prepare_phase_geometry
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(probe, 'prepare_phase_geometry', counted)
    candidate, _, _ = probe.candidate_function()
    for x in ([0, 0], [1, 2], [3, 4]):
        candidate(p, x, geometry_only=True)
    assert len(calls) == 1
    with pytest.raises(ValueError, match='read-only'):
        p._probe_phase_geometry[3][0][0][0, 0] = 99
    p.reference += 1e6
    with pytest.raises(ValueError, match='extrapolat'):
        candidate(p, [0, 0], geometry_only=True)
