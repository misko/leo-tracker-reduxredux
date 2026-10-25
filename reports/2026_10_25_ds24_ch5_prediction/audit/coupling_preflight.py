"""Independent frozen-Gamma parent-coupling preflight; no corpus evaluation."""
import hashlib
import json
from pathlib import Path
import sys
import time

import pytest

HERE = Path(__file__).resolve().parent
SCI = HERE.parent / 'parent_coupling'
sys.path.insert(0, str(SCI))


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    began = time.monotonic()
    output = HERE / 'coupling_preflight.json'
    if output.exists():
        raise FileExistsError('preserve preflight')
    protocol = read(SCI / 'protocol.json')
    digest = sha(SCI / 'protocol.json')
    checks = []

    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))

    bad = [path for path, expected in protocol['files'].items() if sha(path) != expected]
    check('all frozen actual source/metadata/causal-data bindings intact', not bad,
          bindings=len(protocol['files']), mismatches=bad)
    check('no corpus call before preflight; bounded fixed panel and conditional scope',
          not (SCI / 'execution_started.json').exists() and protocol['maximum_scientific_seconds'] == 300 and
          protocol['workers'] == protocol['BLAS_threads'] == 1 and protocol['position_fits'] == 0 and
          protocol['no_GPS'] and protocol['selected_phase_is_not_original_Student_marginal'] and
          [s['case'] for s in protocol['selections']] == ['DS24-0010', 'DS24-0011'] and
          tuple(protocol['offsets_km']) == (-.05, -.025, 0., .025, .05))
    # Independent reconstruction of the selection from the frozen RF-only table.
    for selection in protocol['selections']:
        case = selection['case']
        path = Path('/srv/bulk/leo/research/ds24-bottlenecks-20261024/information') / (case + '.json')
        arm = read(path)['arms']['c0']
        info = arm[selection['source_information_kind']]
        supported = {row['norad'] for row in arm['physical_orbit_metadata'].values()}
        eligible = [(abs(row['weak_axis_correlation']), int(row['coordinate'].split('NORAD')[1]))
                    for row in info['correlations']['top_weak_axis_correlates']
                    if row['coordinate'].startswith('phase_NORAD') and int(row['coordinate'].split('NORAD')[1]) in supported]
        expected = sorted(eligible, key=lambda pair: (-pair[0], pair[1]))[0][1]
        check('archived supported-family RF-only nomination reproduced: ' + case, expected == selection['norad'])
    status = pytest.main(['-q', '-p', 'no:cacheprovider', str(SCI / 'test_coupling.py')])
    check('four final-source affine-Gaussian/rank3/dense/integration/narrow-proposal tests rerun', status == 0)
    driver = (SCI / 'driver.py').read_text()
    math = (SCI / 'coupling_math.py').read_text()
    check('matched physical-law guard and no shape/phase doublecounting explicit',
          "certificate['inner_visible_intervals']==[[-15.,15.]]" in driver and
          "not certificate['unresolved_intervals']" in driver and "not certificate['root_brackets']" in driver and
          "removed=np.r_[phase_slot,mode_slots]" in math and
          "keep[removed]=False" in math and "data['mode_precision']" in driver and
          "if branch=='frozen':b=np.broadcast_to(data['frozen_modes'],b.shape)" in math)
    check('same nonlinear mean, normalized conditional Normal and explicit resolved-mode limitation',
          'proposal_domain_mass' in math and 'prior_domain_mass' in math and 'global_mode_certificate=False' in math and
          'prior/proposal' in (SCI / 'PROTOCOL.md').read_text() and
          protocol['score_tolerance'] == protocol['gradient_tolerance_per_km'] == 1e-3)
    check('original source/input bytes still immutable after pure fixture checks',
          digest == sha(SCI / 'protocol.json') and all(sha(path) == h for path, h in protocol['files'].items()))
    elapsed = time.monotonic() - began
    prior = read(HERE / 'preflight02.json')['cumulative_audit_seconds']
    receipt = dict(all_passed=all(c['passed'] for c in checks), protocol_sha256=digest,
        source_sha256=sha(__file__), checks=checks, seconds=elapsed,
        cumulative_audit_seconds=prior + elapsed, audit_cap_seconds=180,
        corpus_propagation_calls=0, position_fits=0, geographic_truth_read=False,
        interpretation='One active supported family per case under frozen-Gamma conditional Normal; exact nominal phase common, only B(phi) changes. Resolved-mode numerical stability is not a global phase-mode certificate, full VI/Student evidence or achieved displacement.',
        authorization='standing coordinator plan permits bounded 300-second no-fit run on this exact preflight pass')
    receipt['all_passed'] &= receipt['cumulative_audit_seconds'] <= 180
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], protocol_sha256=digest,
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'], failed=[c for c in checks if not c['passed']])))


if __name__ == '__main__':
    main()
