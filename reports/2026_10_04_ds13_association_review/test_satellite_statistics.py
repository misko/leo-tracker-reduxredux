import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent


def test_matched_counts_and_aggregation():
    rows = list(csv.DictReader((HERE / 'satellite-statistics/satellites.csv').open()))
    tracks = list(csv.DictReader((HERE / 'satellite-statistics/receiver-tracks.csv').open()))
    assert len(rows) == 130
    for scan, expected, nsat in [('A', 3644, 33), ('B', 3460, 32)]:
        for arm in ('fitted-c', 'zero-c'):
            selected = [r for r in rows if r['scan'] == scan and r['arm'] == arm]
            assert len(selected) == nsat
            assert sum(int(r['n']) for r in selected) == expected
            for r in selected:
                assert int(r['rx0_n']) + int(r['rx1_n']) == int(r['n'])
                assert int(r['visible_n']) == int(r['n'])
                assert 0 <= float(r['wrong_pct']) <= 100
                np.testing.assert_allclose(float(r['gradient_strength']), np.hypot(float(r['east_gradient']), float(r['north_gradient'])))
                rr = [t for t in tracks if (t['scan'], t['arm'], t['satellite']) == (scan, arm, r['satellite'])]
                for key, subkey in [('rms_hz', 'raw_rms_hz'), ('linear_rms_hz', 'linear_rms_hz'), ('quadratic_rms_hz', 'quadratic_rms_hz')]:
                    pooled = np.sqrt(sum(int(t['n']) * float(t[subkey]) ** 2 for t in rr) / int(r['n']))
                    np.testing.assert_allclose(pooled, float(r[key]))


def test_60412_reproduces_previous_audit():
    tracks = list(csv.DictReader((HERE / 'satellite-statistics/receiver-tracks.csv').open()))
    previous = json.loads((HERE / 'satellite-60412/receipt.json').read_text())
    for r in tracks:
        if r['satellite'] != '60412':
            continue
        old = next(t for t in previous['metrics'] if t['model'] == 'roof' and t['arm'] == r['arm'] and t['rx'] == int(r['rx']) and t['channel'] == 0 and t['channel_controlled'])
        for key in ['raw_rms_hz', 'linear_rms_hz', 'quadratic_rms_hz']:
            np.testing.assert_allclose(float(r[key]), old[key], atol=1e-8)
