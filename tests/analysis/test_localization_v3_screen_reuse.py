import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import algo07v3_prescreen_geometry_oracle as oracle
import numpy as np
import pytest
from check_algo07v3_scan_likelihood import fingerprint

from leo.analysis.localization_v3 import residual_screen as owned
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid


def test_serial_screen_oracle_is_frozen():
    assert hashlib.sha256(Path(oracle.__file__).read_bytes()).hexdigest() == (
        'c605070f6fc7433c727c6e4df746f9766570bfa9b161c18c5dc6f7a6cbc5a9b4'
    )


@pytest.mark.parametrize('policy', list(owned.POLICIES))
def test_full_screen_and_callbacks_match_original_for_all_policies(monkeypatch, policy):
    grid = np.arange(-40., 341.)
    position = np.stack([np.column_stack([np.full(len(grid), 7000. + i * 100),
                                         7 * grid + i * 200, np.full(len(grid), 100. + i * 300)])
                         for i in range(4)])
    velocity = np.zeros_like(position)
    velocity[:, :, 1] = 7.
    bank = dict(time_s=grid, position_km=position, velocity_km_s=velocity)
    region = SearchRegion((0., 0.))
    positions = dict(c0=[0., 0.], fitted_c=[3., 4.])
    cutoff = 1_000_000_000_000_000
    catalogue = dict(cutoff_utc_ns=cutoff, elements={
        str(i + 1): dict(lines=['placeholder', 'placeholder'],
                        element_epoch_utc_ns=cutoff - int(age * 3.6e12),
                        collected_utc_ns=cutoff - int(age * 3.6e12))
        for i, age in enumerate([12., 52., 65., 20.])})
    targets = []
    for index, rf in enumerate([11.5e9, 12.5e9]):
        times = np.arange(0., 120., 3.) + index
        corrected = {arm: phase_frequency_grid(bank, times, *region.latlon(x),
                                               phase_seconds=2.)[0][index] * rf / 11.5e9
                     + np.sin(times) * 2 for arm, x in positions.items()}
        targets.append(dict(source=dict(rf_hz=rf, component=f'target-{index}'),
                            times_s=times, corrected_hz=corrected))
    packet = dict(case='synthetic', scan_receipt=dict(cutoff_utc_ns=cutoff, origin_utc_ns=cutoff),
                  positions=positions, targets=targets)
    for module in (oracle, owned):
        monkeypatch.setattr(module, 'Satrec', SimpleNamespace(twoline2rv=lambda *a: None))
        monkeypatch.setattr(module, 'ecef_states', lambda *a: (
            position.copy(), velocity.copy(), np.array([True, True, True, False])))
    expected_callbacks, callbacks = [], []
    expected = oracle.screen_candidates(copy.deepcopy(packet), catalogue, region, policy=policy,
                                        on_target=expected_callbacks.append)
    actual = owned.screen_candidates(copy.deepcopy(packet), catalogue, region, policy=policy,
                                     on_target=callbacks.append)
    assert fingerprint(actual) == fingerprint(expected)
    assert fingerprint(callbacks) == fingerprint(expected_callbacks)
    assert actual['propagation_failures'] == [4]
    assert all(len(t['folds']) == 4 and t['rows'] for t in actual['targets'])
    callbacks[0]['source']['component'] = 'caller mutation'
    assert actual['targets'][0]['source']['component'] == 'target-0'
