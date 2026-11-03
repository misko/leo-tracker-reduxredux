from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from prepare_recorded_scan_inputs import render
from leo.contracts.digests import canonical_digest


def capture():
    return {'receipt': {'plan': {'geometry': {'sample_rate_hz': 2500000, 'receiver_ids': [0,1]}},
        'events': [{'visit_index': i, 'valid_start_counter': 10**15+i*400000,
                    'valid_end_counter_exclusive': 10**15+i*400000+300000,
                    'decision': {'generation': 1234}, 'actual_if_offset_hz': 2,
                    'target': {'channel': 3, 'edge': edge, 'rf_center_hz': 11209687500}}
                   for i,edge in enumerate(['lower','upper'])]},
        'timing': {'sample_rate_hz': 2500000, 'qualified': True,
                   'session_start_device_sample_counter': 10**15-100,
                   'first_sample_estimate_utc_ns': 1790591085928628419,
                   'first_sample_bracket_width_ns': 363246517}}


def invoke(c):
    return render(c, canonical_digest(c), 'sha256:'+'a'*64, '/iq', '/templates')


def test_original_clock_retunes_and_uncertainty_preserved():
    manifest, authority = invoke(capture())
    rows = [x.split('\t') for x in manifest.splitlines()]
    assert [int(x[1]) for x in rows] == [0,160000000]
    assert rows[0][2] == '/templates/lower-exact.c128'
    assert rows[1][2] == '/templates/upper-exact.c128'
    sources = [x.split('\t') for x in authority.splitlines()]
    assert sources[1][2] == '1790591085928628419'
    assert sources[1][3] == '1234'
    assert sources[1][9:12] == ['1','11209687498','363246517']


@pytest.mark.parametrize('fault', ['clock','dwell','generation','order','rate','edge','overlap'])
def test_invalid_capture_rejected(fault):
    c = capture(); event = c['receipt']['events'][1]
    if fault == 'clock': c['timing']['qualified'] = False
    elif fault == 'dwell': event['valid_end_counter_exclusive'] += 1
    elif fault == 'generation': event['decision']['generation'] += 1
    elif fault == 'order': event['visit_index'] = 0
    elif fault == 'rate': c['timing']['sample_rate_hz'] = 5000000
    elif fault == 'overlap':
        event['valid_start_counter'] -= 200000
        event['valid_end_counter_exclusive'] -= 200000
    else: event['target']['edge'] = 'unknown'
    with pytest.raises(ValueError): invoke(c)


def test_wrong_capture_identity_rejected():
    with pytest.raises(ValueError, match='digest mismatch'):
        render(capture(), 'sha256:'+'b'*64, 'sha256:'+'a'*64, '/iq', '/templates')
