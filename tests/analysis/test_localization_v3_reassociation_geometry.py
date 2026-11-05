import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import algo07v3_prereassociation_geometry_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import reassociation_screen as owned
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


def test_original_reassociation_screen_is_frozen():
    assert hashlib.sha256(Path(oracle.__file__).read_bytes()).hexdigest() == (
        '1a4bdceb73c75a3638c63f0fff74ea34cf1a5b4932c54f9fd29f1cca102b8750')


@pytest.mark.parametrize('scenario', ['retained', 'mixed', 'invisible', 'tied_lengths'])
def test_complete_screen_and_arm_major_receipts_match_original(monkeypatch, scenario):
    grid = np.arange(-40., 341.)
    position = np.stack([np.column_stack([np.full(len(grid), 7000. + i * 300),
                                         (7. + i) * grid + i * 200,
                                         np.full(len(grid), 100. + i * 300)])
                         for i in range(3)])
    velocity = np.zeros_like(position)
    for i in range(3):
        velocity[i, :, 1] = 7. + i
    if scenario == 'invisible':
        position[0, :, 0] *= -1
    bank = dict(time_s=grid, position_km=position, velocity_km_s=velocity)
    region = SearchRegion((0., 0.))
    tracks = []
    lengths = [30, 30, 30] if scenario == 'tied_lengths' else [20, 36, 28]
    for k, count in enumerate(lengths):
        times = np.linspace(10. + k, 130. + k, count)
        rf = 11.5e9 + k * 0.1e9
        j = k % 2 if scenario == 'mixed' else 0
        values = phase_frequency_grid(bank, times, *region.latlon([0., 0.]))[0][j] * rf / 11.5e9
        tracks.append(dict(key=f'track-{k}', times=times, rf_hz=rf, receiver=1,
                           values=values + np.sin(times) * 3))
    scan = SimpleNamespace(tracks=tracks, search_region=region,
                           hardware=lambda tr, beta: np.zeros(len(tr['times'])),
                           rx_basis=[np.zeros((n, 1)) for n in lengths])
    bounds = np.r_[0, np.cumsum(lengths)]
    base = SimpleNamespace(keep=np.ones(sum(lengths), bool), members=list(range(3)),
                           rows=[dict(candidate_norad=1) for _ in lengths],
                           slices=[slice(a, b) for a, b in
                                   zip(bounds[:-1], bounds[1:], strict=True)])
    d = dict(scan=scan, problems={a: (base, np.zeros(2)) for a in owned.ARMS})
    calls = []

    def refit(context, arm, start, **kwargs):
        calls.append(arm)
        return dict(x=np.array([0., 0.] if arm == 'c0' else [1., -1.]),
                    reference=np.zeros(1))

    def build(context, arm, reference, **kwargs):
        return SimpleNamespace(scan=scan, state=lambda x: dict(
            beta=np.zeros(1), smooth=np.zeros((2, 1)))), None

    for module in (oracle, owned):
        monkeypatch.setattr(module, 'refit', refit)
        monkeypatch.setattr(module, 'build', build)
    expected = oracle.screen(copy.deepcopy(d), 1, np.arange(1, 4), copy.deepcopy(bank))
    assert calls == ['c0', 'fitted_c']
    calls.clear()
    actual = owned.screen(copy.deepcopy(d), 1, np.arange(1, 4), copy.deepcopy(bank))
    assert calls == ['c0', 'fitted_c']
    assert fingerprint(actual) == fingerprint(expected)
    longest = sorted(range(3), key=lambda k: -lengths[k])[:2]
    assert [(r['arm'], r['track']) for r in actual['coarse']] == [
        (a, f'track-{k}') for a in owned.ARMS for k in longest]
    if scenario == 'invisible':
        assert actual['status'] == 'incumbent_not_visible_over_complete_phase_grid'
