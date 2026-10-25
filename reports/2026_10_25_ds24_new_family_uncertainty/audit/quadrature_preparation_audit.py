"""Independently reconstruct preparation decisions from every scalar record."""

import collections
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREP = ROOT/'scientific/preparation02'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    protocol = read(PREP/'protocol.json')
    result = read(PREP/'result.json')
    digest = sha(PREP/'protocol.json')
    assert read(PREP/'protocol_seal.json')['protocol_sha256'] == result['protocol_sha256'] == digest
    assert result['status'] == 'complete' and result['all_passed']
    assert result['position_fits'] == 0 and result['fit_launch_authorized'] is False
    assert result['seconds'] <= protocol['preparation_seconds_cap'] == 600
    assert protocol['domain_s'] == [-15., 15.] and protocol['hard_node_cap'] == 2561
    assert protocol['score_absolute_tolerance'] == protocol['position_gradient_absolute_tolerance_per_km'] == 1e-3
    assert protocol['central_difference_step_km'] == .01
    assert protocol['prior_mass_absolute_tolerance'] == 1e-8
    assert protocol['target_phase_refresh'] is False and protocol['target_noise_learning'] is False
    assert protocol['fit_launch_authorized'] is False
    assert sha(ROOT/'COORDINATOR_PLAN.md') == protocol['coordinator_plan_sha256']
    assert sha(ROOT/'PHASE_INTEGRATION_AMENDMENT.md') == protocol['amendment_sha256']
    for path, digest in protocol['source_sha256'].items():
        assert sha(path) == digest, path
    counts = protocol['candidate_counts']
    assert counts == [81, 161, 321, 641, 1281, 2561]
    groups = collections.defaultdict(dict)
    hashes = {}
    for path in sorted((PREP/'points').glob('*.json')):
        record = read(path)
        key = tuple(record[field] for field in ('case', 'arm', 'center', 'branch'))
        index = record['point_index']
        assert index not in groups[key]
        assert set(record['rules']) == set(map(str, counts))
        assert record['adaptive']['relative_integral_error'] <= 1e-6
        for values in record['rules'].values():
            assert min(values['minimum_node_elevation_deg'], values['minimum_domain_endpoint_elevation_deg']) > 0
        groups[key][index] = record
        hashes[str(path)] = sha(path)
    assert len(hashes) == 160 and len(groups) == 32
    expected_keys = {(case, arm, center, branch)
        for case in protocol['cases'] for arm in protocol['arms']
        for center in ('baseline', 'support', 'midpoint', 'cold_regional_start') for branch in protocol['branches']}
    assert set(groups) == expected_keys
    reported = {tuple(row[field] for field in ('case', 'arm', 'center', 'branch')):row for row in result['rows']}
    assert set(reported) == expected_keys
    maxima = {str(n):collections.defaultdict(float) for n in counts}
    passed = {str(n):True for n in counts}
    for key, indexed in groups.items():
        assert set(indexed) == set(range(5))
        records = [indexed[k] for k in range(5)]
        center = np.asarray(records[0]['position_east_north_km'])
        for index, offset in enumerate(([.01, 0], [-.01, 0], [0, .01], [0, -.01]), 1):
            np.testing.assert_allclose(np.asarray(records[index]['position_east_north_km'])-center, offset, rtol=0, atol=1e-14)
        def gradient(values):
            return np.array([(values[1]-values[2])/.02, (values[3]-values[4])/.02])
        adaptive = [record['adaptive']['objective'] for record in records]
        dense = [record['rules']['2561']['objective'] for record in records]
        for count in counts:
            name = str(count)
            values = [record['rules'][name]['objective'] for record in records]
            checks = dict(score_error_vs_adaptive=max(abs(np.asarray(values)-adaptive)),
                score_error_vs_denser=max(abs(np.asarray(values)-dense)),
                gradient_error_vs_adaptive_per_km=max(abs(gradient(values)-gradient(adaptive))),
                gradient_error_vs_denser_per_km=max(abs(gradient(values)-gradient(dense))),
                prior_mass_error=max(abs(record['rules'][name]['quadrature_prior_mass']-1) for record in records))
            ok = all(value <= (1e-8 if field == 'prior_mass_error' else 1e-3) for field, value in checks.items())
            assert reported[key]['checks'][name]['passed'] == ok
            for field, value in checks.items():
                np.testing.assert_allclose(value, reported[key]['checks'][name][field], rtol=0, atol=1e-14)
                maxima[name][field] = max(maxima[name][field], float(value))
            passed[name] &= ok
    eligible = [n for n in counts[:-1] if passed[str(n)]]
    assert min(eligible) == result['global_fixed_node_count'] == 1281
    phase_domain = read(ROOT/'math_audit/phase_domain.json')
    # The independent domain receipt is bound for review; its own formula/scale
    # and actual numerical integration are audited by the math reviewer.
    output = dict(all_passed=True, no_position_fits=True, GPS_used=False,
        preparation_protocol_sha256=sha(PREP/'protocol.json'), preparation_result_sha256=sha(PREP/'result.json'),
        independent_phase_domain_sha256=sha(ROOT/'math_audit/phase_domain.json'),
        source_sha256=sha(Path(__file__)), point_sha256=hashes,
        reconstructed_point_records=len(hashes), reconstructed_center_branch_gradient_checks=len(groups),
        global_fixed_node_count=1281, accepted_candidate_counts=eligible, maximum_errors_by_count=dict(maxima),
        phase_laws=result['phase_laws'], preparation_seconds=result['seconds'],
        first_order_approximation_remains_rejected=True,
        target_association_qualified=False, operational_policy='saved_baseline',
        scientific_launch_approved=False,
        caveat='Decision arithmetic and source/input seals independently verified. Separate math audit must verify actual likelihood integration, and final endpoint convergence remains mandatory.')
    with (HERE/'quadrature_preparation_audit.json').open('x') as stream:
        json.dump(output, stream, indent=2); stream.write('\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('point_sha256', 'maximum_errors_by_count', 'phase_laws')}, indent=2))
    print('selected-rule maximum errors:', dict(maxima['1281']))


if __name__ == '__main__':
    main()
