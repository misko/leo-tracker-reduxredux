"""Bounded full-panel quadrature verification before donor calibration."""
import json
import time
from pathlib import Path

from regression_batch import digest, verify_sources
from shared_offset_integral import integrate

HERE = Path(__file__).resolve().parent
started = time.monotonic()
path = HERE/'offset-candidate-groups-v1.json'
assert digest(path) == path.with_suffix('.sha256').read_text().strip()
data = json.loads(path.read_text())
verify_sources(data['source_sha256'])
verify_sources(data['input_sha256'])
sources = dict(data['source_sha256'])
for name in ['audit_shared_offset_integral.py', 'shared_offset_integral.py']:
    sources[str(HERE/name)] = digest(HERE/name)
rows = []
for track in data['rows']:
    if time.monotonic()-started > 60:
        break
    initial = time.monotonic()
    previous = integrate(track['groups'], track['offset_scale_hz'], track['df'], 50., .94, 8)
    checks = []
    passed = False
    for order in [16, 32, 64]:
        current = integrate(track['groups'], track['offset_scale_hz'], track['df'], 50., .94, order)
        difference = max(abs(current[k]-previous[k]) for k in ['shared', 'independent'])
        checks.append(dict(order=order, difference=difference, prior_mass=current['prior_mass']))
        if difference < 1e-6 and abs(current['prior_mass']-1) < 1e-8:
            passed = True
            break
        previous = current
    rows.append(dict(unit=track['unit'], track=track['track'], groups=len(track['groups']),
        passed=passed, checks=checks, result=current, seconds=time.monotonic()-initial))
verify_sources(sources)
result = dict(rows=rows, planned=len(data['rows']), completed=len(rows), passed=sum(r['passed'] for r in rows),
    max_order=max(r['checks'][-1]['order'] for r in rows), seconds=time.monotonic()-started,
    source_sha256=sources, input_sha256={str(path): digest(path)},
    config=dict(noise_scale_hz=50., signal_probability=.94, log_tolerance=1e-6, prior_mass_tolerance=1e-8),
    qualification='Numerical assay with fixed engineering parameters only, not donor-calibrated '
    'predictive comparison or geographic improvement. One offset shared per track versus '
    'independent per-group offsets with the same one-group marginals. Piecewise quadrature '
    'covers every candidate peak; wrapped Student prior has an explicit omitted-tail bound. '
    'Agreement of successive orders is a numerical check, not a formal quadrature bound. '
    'No GPS, localization fits, or RF. Incomplete/failed integrals retained.')
output = HERE/'shared-offset-integral-audit-v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
output.with_suffix('.sha256').write_text(digest(output)+'\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['rows', 'source_sha256', 'input_sha256']}, indent=2))
