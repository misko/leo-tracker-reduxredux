"""Independent provenance and held-error aggregation checks; no refit."""
import hashlib
import json
import math
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
path = HERE/'outcome.json'
data = json.loads(path.read_text())
for name, expected in data['sources'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == expected
scans = {}
for index in range(0,32,4):
    sources = {}
    for row in data['rows']:
        assert row['training_rows'] >= 6
        assert len(row['constant_absolute_errors_hz']) == row['held_rows']
        assert len(row['drift_absolute_errors_hz']) == row['held_rows']
        assert 0 <= row['applied_rows'] <= row['held_rows']
        if row['fit'] is not None:
            assert row['donor_count'] >= 3 and abs(row['fit'][0]) <= 20
        if row['scan_index'] != index or not row['held_rows']:
            continue
        gain = math.fsum(a-b for a,b in zip(row['constant_absolute_errors_hz'], row['drift_absolute_errors_hz']))/row['held_rows']
        assert abs(gain-row['mean_gain_hz']) < 1e-9
        sources.setdefault(row['norad'], []).append(gain)
    scans[index] = math.fsum(math.fsum(v)/len(v) for v in sources.values())/len(sources)
    assert abs(scans[index]-data['summary']['scan_gains_hz'][str(index)]) < 1e-9
gains = list(scans.values())
assert data['summary']['gate_pass'] == (sum(g>0 for g in gains)>=5 and math.fsum(gains)>0 and median(gains)>0)
slopes = [r['fit'][0] for r in data['rows'] if r['fit'] is not None]
result = dict(provenance_and_aggregation_pass=True, replays_measurement_predictions=False,
              paired_wins=sum(r['mean_gain_hz']>0 for r in data['rows'] if r['mean_gain_hz'] is not None),
              evaluated_pairs=sum(r['held_rows']>0 for r in data['rows']),
              slope_min_hz_s=min(slopes), slope_median_hz_s=median(slopes), slope_max_hz_s=max(slopes),
              outcome_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
              verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
