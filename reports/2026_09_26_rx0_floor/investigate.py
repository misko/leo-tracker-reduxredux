"""Read-only, bounded audit of stored IQ; never opens a radio or modifies captures.

Run with the repository Python and read access to /srv/bulk/leo. JSON goes to stdout.
RMS is per real ADC component, including DC, in stored ci16 counts (not dBm).
"""

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import zstandard


ROOT = Path('/srv/bulk/leo')
TARGET = 'scan-fw-2e6b78f0cd0cbbbc'
SESSIONS = [
    'scan-fw-e24a267710fdd336',
    'scan-fw-ed1fe3d3ccf5fd45',
    'scan-fw-ce1f8e4ca49fce5c',
    TARGET,
]
decoder = zstandard.ZstdDecompressor()
result = {'target': TARGET, 'sessions': [], 'analysis': {}}


def digest(payload):
    return 'sha256:' + hashlib.sha256(payload).hexdigest()


for session in SESSIONS:
    directory = ROOT / 'scanner-adaptive-recordings' / session
    envelope = json.loads((directory / 'manifest.json').read_bytes())
    manifest = envelope['manifest']
    receipt = manifest['receipt']
    rows = []
    for chunk in manifest['chunks'][::20 if session == TARGET else 80]:
        compressed = (directory / chunk['relative_path']).read_bytes()
        raw = decoder.decompress(compressed, max_output_size=chunk['uncompressed_bytes'])
        assert digest(compressed) == chunk['compressed_sha256']
        assert digest(raw) == chunk['uncompressed_sha256']
        assert len(raw) == chunk['uncompressed_bytes']
        values = np.frombuffer(raw, dtype='<i2').reshape(chunk['sample_count'], 2, 2)
        x = values.astype(np.float64)
        event = receipt['events'][chunk['first_visit_index']]
        rows.append({
            'visit': chunk['first_visit_index'],
            'channel': event['target']['channel'],
            'rms_counts': np.sqrt(np.mean(x*x, axis=(0, 2))).tolist(),
            'iq_mean_counts': np.mean(x, axis=0).tolist(),
            'iq_std_counts': np.std(x, axis=0).tolist(),
            'zero_fraction': np.mean(values == 0, axis=(0, 2)).tolist(),
            'peak_abs_counts': np.max(np.abs(x), axis=(0, 2)).tolist(),
            'identical_receiver_fraction': float(np.mean(np.all(values[:, 0] == values[:, 1], axis=1))),
        })
    groups = {}
    for channel in range(1, 5):
        a = np.array([r['rms_counts'] for r in rows if r['channel'] == channel])
        groups[str(channel)] = {
            'sampled_visits': len(a),
            'median_rms_counts': np.median(a, axis=0).tolist(),
            'median_rx1_over_rx0_db': float(np.median(20*np.log10(a[:, 1]/a[:, 0]))),
        }
    result['sessions'].append({
        'session': session,
        'manifest_sha256': envelope['sha256'],
        'start_utc': datetime.fromtimestamp(manifest['timing']['first_sample_estimate_utc_ns']/1e9, timezone.utc).isoformat(),
        'gain_db': receipt['plan']['geometry']['gain_db'],
        'sample_rate_hz': receipt['plan']['geometry']['sample_rate_hz'],
        'radio_serial': receipt['radio_serial'],
        'total_visits': receipt['complete_visit_count'],
        'sampled_visits': len(rows),
        'median_rms_counts': np.median([r['rms_counts'] for r in rows], axis=0).tolist(),
        'by_channel': groups,
        'rows': rows,
    })

analysis = ROOT / 'scanner-adaptive-analysis' / TARGET
metrics_paths = list(analysis.glob('*/metrics-manifest.v8.json'))
assert len(metrics_paths) == 1
metrics_path = metrics_paths[0]
metrics = json.loads(metrics_path.read_bytes())['document']
assert metrics['input_manifest_sha256'] == result['sessions'][-1]['manifest_sha256']
receivers = defaultdict(list)
for entry in metrics['visits']:
    compressed = (metrics_path.parent / entry['relative_path']).read_bytes()
    raw = decoder.decompress(compressed, max_output_size=entry['uncompressed_bytes'])
    assert digest(compressed) == entry['compressed_sha256']
    assert digest(raw) == entry['uncompressed_sha256']
    document = json.loads(raw)['document']
    for probe in document['probes']:
        candidates = probe['candidates']
        receivers[probe['receiver_id']].append({
            'visit': document['visit_index'],
            'max_margin': max((c['fractional_margin'] for c in candidates), default=0),
            'passed_candidates': sum(c['passed_fractional_margin_gate'] for c in candidates),
        })
for receiver, rows in receivers.items():
    result['analysis'][str(receiver)] = {
        'probes': len(rows),
        'passing_probes': sum(r['passed_candidates'] > 0 for r in rows),
        'passing_candidates': sum(r['passed_candidates'] for r in rows),
        'max_margin_quantiles_0_50_90_99_100': np.quantile([r['max_margin'] for r in rows], [0, .5, .9, .99, 1]).tolist(),
        'passing_visits': [r for r in rows if r['passed_candidates'] > 0],
    }
print(json.dumps(result, indent=2))
