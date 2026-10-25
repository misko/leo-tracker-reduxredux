"""Hash and physical-input review of the preserved, non-launch preparation."""

import hashlib
import json
from pathlib import Path

import numpy as np
import recovery as original

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PREPARATION = ROOT/'scientific/preparation01'


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    seal = read(PREPARATION/'preparation_seal.json')
    assert seal['position_fits'] == 0 and seal['fit_launch_authorized'] is False
    assert seal['no_GPS'] and seal['first_order_phase_material_limitation']
    assert seal['coordinator_plan_sha256'] == sha(ROOT/'COORDINATOR_PLAN.md')
    for path, digest in seal['source_sha256'].items():
        assert sha(path) == digest, path
    assert sha(PREPARATION/'input_bindings.json') == seal['input_sha256']
    assert sha(PREPARATION/'deleted_prior_projections.json') == seal['deleted_prior_projections_sha256']
    assert sha(ROOT/'math_audit/phase_linearization.json') == seal['independent_phase_audit_sha256']
    inputs = read(PREPARATION/'input_bindings.json')
    audit = read(HERE/'parent_audit.json')
    assert audit['all_passed'] and audit['no_position_fits'] and audit['GPS_used'] is False
    for path, digest in audit['source_sha256'].items():
        assert sha(path) == digest, path
    rows = []
    for case, frozen in inputs.items():
        binding = read(HERE/(case+'_target_binding.json'))
        target = frozen['target']
        d = original.context(case)
        for field in ('component', 'candidate_index', 'norad', 'receiver', 'channel', 'rf_hz', 'alias', 'observation_ids'):
            assert target[field] == binding[field], field
        np.testing.assert_array_equal(frozen['target_times_s'], binding['times_s'])
        np.testing.assert_array_equal(frozen['target_graph_values_hz'], binding['graph_values_hz'])
        assert [o['observation_id'] for o in frozen['target_native_observations']] == binding['observation_ids']
        np.testing.assert_array_equal([o['measured_cfo_hz'] for o in frozen['target_native_observations']], binding['native_measured_cfo_hz'])
        for observation, time_s in zip(frozen['target_native_observations'], binding['times_s'], strict=True):
            assert observation['receiver'] == binding['receiver'] and observation['channel'] == binding['channel']
            assert observation['actual_rf_hz'] == binding['rf_hz'] and observation['time_s'] == time_s
        np.testing.assert_allclose(frozen['target_alias_values_hz'],
            np.asarray(binding['graph_values_hz'])+binding['alias']*(1/(4.4e-6)), atol=1e-9, rtol=0)
        sl = d['base'].slices[target['row_index']]
        np.testing.assert_array_equal(frozen['target_original_point_noise_hz'], d['base'].point_noise[sl])
        assert frozen['parent_node'] == d['node'] and frozen['parent_predictive_entries'] == d['entries']
        for field, original_field in [('original_mask', 'keep'), ('powers', 'powers'), ('causal_phase_means', 'means')]:
            np.testing.assert_array_equal(frozen[field], d[original_field])
        assert frozen['model'] == d['model']
        assert target['phase_mean_s'] == d['all_means'][target['candidate_index']]
        assert target['phase_sd_s'] == d['widths'][target['candidate_index']]
        assert target['phase_nu'] == d['model']['nu'] == 3
        assert frozen['target_constant_prior_sd_hz'] == 300
        element = frozen['target_element']['provenance']
        assert element['norad'] == target['norad']
        assert max(element['element_epoch_utc_ns'], element['collected_utc_ns']) <= frozen['causal_cutoff_utc_ns']
        for path, digest in frozen['source_hashes'].items():
            assert sha(path) == digest, path
        rows.append(dict(case=case, points=target['points'], target_binding_sha256=sha(HERE/(case+'_target_binding.json')),
                         original_point_noise_verified=True, original_parent_contract_verified=True,
                         target_causal_phase_and_TLE_verified=True))
    tests = read(PREPARATION/'test_receipt.json')
    assert tests['passed'] and tests['tests'] == 9 and tests['position_fits'] == 0
    result = dict(construction_and_inputs_passed=True, physical_phase_adequacy_passed=False,
        position_fits=0, GPS_used=False, fit_launch_authorized=False,
        preparation_seal_sha256=sha(PREPARATION/'preparation_seal.json'),
        source_sha256=sha(Path(__file__)), parent_audit_sha256=sha(HERE/'parent_audit.json'), rows=rows,
        independent_test_rerun=dict(tests=9, passed=True, seconds=5.904, numerical_threads=1,
            scope='owned adapter tests, including repeated-position cache invariance and unchanged parent replay'),
        unresolved='First-order phase approximation is materially inaccurate; nonlinear integration requires separate version, convergence audit and coordinator go.')
    with (HERE/'preparation01_audit.json').open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
