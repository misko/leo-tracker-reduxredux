import json
from pathlib import Path

import numpy as np

from investigate_60412 import diagnostic_prediction
from association_audit import polynomial_audit


def test_diagnostic_matches_audit():
    t = np.linspace(60, 105, 120)
    ch = np.arange(120) % 3
    y = 40 * ch + 2 * (t - 80) + .2 * (t - 80) ** 2 + np.sin(t)
    summary = polynomial_audit(t, y, ch, True)
    for degree, key in [(1, 'linear_rms_hz'), (2, 'quadratic_rms_hz')]:
        pred = diagnostic_prediction(t, y, ch, degree)
        np.testing.assert_allclose(np.sqrt(np.mean((y - pred) ** 2)), summary[key], atol=1e-10)


def test_saved_case():
    folder = Path(__file__).parent / 'satellite-60412'
    receipt = json.loads((folder / 'receipt.json').read_text())
    d = np.load(folder / 'observations.npz')
    assert len(d['row_id']) == len(set(d['row_id'])) == 240
    assert np.sum(d['rx'] == 0) == 189
    assert np.sum(d['rx'] == 1) == 51
    assert receipt['scan_B_assigned_count'] == 0
    for row in receipt['metrics']:
        assert row['quadratic_rms_hz'] <= row['linear_rms_hz'] + 1e-8
        assert row['linear_rms_hz'] <= row['raw_rms_hz'] + 1e-8
    for row in receipt['pointing']:
        assert row['west_fraction'] == 1
        assert row['own_off_axis_deg']['max'] < 90
        if row['rx'] == 1:
            assert 31 < row['own_off_axis_deg']['min'] < 33
            assert 49 < row['own_off_axis_deg']['max'] < 50
    for arm in ('fitted-c', 'zero-c'):
        assert np.all(d[f'roof_{arm}_nearest_other_id'] != 60412)
        assert np.all(np.isfinite(d[f'roof_{arm}_residual_hz']))
        assert abs(receipt['roof_timing_s'][arm]) < 1
