"""Independent frozen whole-source mixture and serialized-port preflight."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import pytest
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parent.parent
SCI = ROOT / 'ambiguity'
sys.path.insert(0, str(SCI))
import pilot02 as p

read = lambda path: json.loads(Path(path).read_bytes())
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    start = time.monotonic(); checks = []
    def check(name, passed, **detail):
        checks.append(dict(name=name, passed=bool(passed), **detail))
    protocol = read(SCI / 'protocol02.json'); digest = sha(SCI / 'protocol02.json')
    check('exact revised freeze and all scientific input/source bindings',
          digest == 'c50f0dee25838b41c42a42beba40c390a752337270098f27aac62ef0c878f05e' and
          all(sha(path) == value for path, value in protocol['source_input_hashes'].items()),
          bindings=len(protocol['source_input_hashes']))
    def functions(path):
        return {n.name: ast.dump(n) for n in ast.parse(Path(path).read_text()).body if isinstance(n, ast.FunctionDef)}
    old, new = functions(SCI / 'pilot.py'), functions(SCI / 'pilot02.py')
    exempt = {'complete_component', 'freeze', 'verify', 'run'}
    check('narrow prelaunch revision preserves all scientific equations and original freeze',
          all(old[name] == new[name] for name in old.keys() - exempt) and
          sha(SCI / 'protocol.json') == '5a142dbb1742c7dcf32828aced63d0ac68cdf63cb94d854cfd0340fbca9a9d4a' and
          "groups=np.zeros(len(comp['raw']),int)" in (SCI / 'pilot02.py').read_text() and
          not (SCI / 'execution_started.json').exists())
    for case in p.CASES:
        meta = read(SCI / 'prepared' / case / 'metadata.json')
        check(case + ': all eight nonincumbents share complete native owner and unchanged parent',
              len(meta['pool']) == 8 and meta['all8_families_absent_from_parent_likelihood'] and
              len(set(meta['entry']['observation_ids'])) == meta['entry']['points'] and
              all(not read(SCI / 'prepared' / case / (arm + '_parent.json'))['removed_curved_ids'] and
                  not read(SCI / 'prepared' / case / (arm + '_parent.json'))['removed_predictive_ids'] for arm in p.ARMS))
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(SCI / 'test_pilot02.py')])
    check('eight owned tests independently rerun including all four actual serialized/redacted ports', status == 0)
    # Independent normalized enumeration, rather than invoking the runner's integrator.
    values = np.array([3., 5., 7., 11., 13., 17., 19., 23.]); width = np.linspace(.001, .02, 8)
    physical = [dict(objective=float(v), certified_visibility=True,
        full_support_lower_log_integral=float(-.5*(v+w)),
        full_support_upper_log_integral=float(-.5*(v-w))) for v, w in zip(values, width)]
    unknown = dict(objective=9., reference_passed=True, lower_logZ=-4.500001, upper_logZ=-4.499999)
    for weight in [.25, .5, .75]:
        result = p.mixture(physical, unknown, weight)
        expected = -2*logsumexp(np.r_[np.log(weight/8)-.5*values, np.log(1-weight)-4.5])
        check('normalized whole-owner evidence and interval at physical class weight ' + str(weight),
              abs(result['objective'] - expected) < 1e-12 and result['lower_objective'] <= expected <= result['upper_objective'])
    check('matched both-c arms, fixed probes and original cumulative budget; no fits/GPS/adoption',
          protocol['cases'] == ['DS24-0011', 'DS24-0012'] and protocol['arms'] == ['c0', 'fitted_c'] and
          protocol['physical_contexts'] == 96 and protocol['unknown_contexts'] == 12 and
          protocol['workers'] == 2 and protocol['BLAS_threads'] == 1 and protocol['h_km'] == .1 and
          abs(protocol['preparation_seconds'] + protocol['remaining_seconds'] - 600) < 1e-10 and
          protocol['position_fits'] == 0 and not protocol['GPS_used'] and not protocol['operational_adoption'])
    check('all frozen bindings unchanged after independent pure/prepared-port tests',
          all(sha(path) == value for path, value in protocol['source_input_hashes'].items()))
    result = dict(all_passed=all(row['passed'] for row in checks), protocol_sha256=digest,
        checks=checks, seconds=time.monotonic()-start, source_sha256=sha(__file__),
        new_real_target_density_evaluations=0, orbit_propagation_calls=0, position_fits=0,
        geographic_truth_read=False,
        scope='Conditional proper whole-source evidence and bounded central secants; no calibrated identity probabilities or position-displacement bounds.')
    with (ROOT / 'audit/preflight02.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'], checks=len(checks), seconds=result['seconds'],
        failed=[row for row in checks if not row['passed']])))


if __name__ == '__main__':
    main()
