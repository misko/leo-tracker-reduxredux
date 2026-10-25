"""Independent saved-result audit; no propagation, fitting or real geography."""
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent / 'synthetic'
OLD = Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/synthetic')
sys.path.insert(0, '/home/mouse9911/gits/leo-tracker-reduxredux/tools')
from run_ds23_combined_recovery_full import valid


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = read(ROOT / 'protocol.json')
    seal = read(ROOT / 'scientific_seal.json')
    assert seal['protocol_sha256'] == sha(ROOT / 'protocol.json')
    for path, digest in seal['files'].items():
        assert sha(Path(path)) == digest, path
    for path, digest in protocol['source_sha256'].items():
        assert sha(Path(path)) == digest, path
    execution = read(ROOT / 'execution.json')
    expected = set(itertools.product(protocol['cases'], range(2), protocol['noisy_variants'],
                                     protocol['interventions'], protocol['arms']))
    rows = execution['rows']
    keys = [(r['case'], r['site_index'], r['variant'], r['intervention'], r['arm']) for r in rows]
    assert len(keys) == len(set(keys)) == 32 and set(keys) == expected
    max_error = 0.
    max_scalar_offset_change = 0.
    max_decomposition = 0.
    accepted = 0
    paired_observations = {}
    groups = {}
    for row in rows:
        assert row['status'] == 'complete' and not row['real_GPS_used']
        x = np.asarray(row['endpoint_east_north_km'])
        truth = np.asarray(row['artificial_position_east_north_km'])
        error = float(np.linalg.norm(x - truth))
        max_error = max(max_error, abs(error-row['synthetic_position_error_km']))
        assert np.max(abs(x)) <= 12.5
        np.testing.assert_allclose(x-truth, row['error_vector_east_north_km'], rtol=0, atol=1e-12)
        control = OLD / 'fits' / row['case'] / f"site{row['site_index']}" / row['variant'] / row['arm'] / 'result.json'
        assert sha(control) == row['control_result_sha256']
        old = read(control)
        assert old['synthetic_position_error_km'] == row['paired_control_error_km']
        q = row['qualification']
        original = valid({arm: row for arm in protocol['arms']})
        phase = float(np.max(abs(np.asarray(row['state']['phases']))))
        gamma = row['fixed_objective_diagnostics']['endpoint_at_final_reference']['final_log_precision_change'] <= 1e-5
        passed = bool(original and phase <= 15.000001 and row['final_phase_change_s'] <= .01 and gamma)
        assert q['original_single_arm_valid'] == original and q['passed'] == passed
        accepted += passed
        diag = row['fixed_objective_diagnostics']
        offsets = []
        for key in ('endpoint_at_final_reference','truth_at_final_reference','truth_at_true_phase_reference'):
            d = diag[key]
            offsets.append(d['optimizer_scalar']-d['total_negative_twice_elbo'])
            closure = d['total_negative_twice_elbo']-d['parent_negative_twice_elbo']-d['predictive_objective']
            max_decomposition = max(max_decomposition, abs(closure), abs(d['parent_decomposition_closure']))
        max_scalar_offset_change = max(max_scalar_offset_change, max(offsets)-min(offsets))
        pair_key = (row['case'],row['site_index'],row['variant'],row['intervention'])
        paired_observations.setdefault(pair_key,set()).add(row['observations_sha256'])
        groups.setdefault((row['intervention'],row['arm']),[]).append((error,row['paired_control_error_km']))
    assert max_error < 1e-12 and max_scalar_offset_change < 1e-8 and max_decomposition < 1e-8
    assert all(len(values)==1 for values in paired_observations.values())
    output = dict(all_passed=True, scientific_seal_sha256=sha(ROOT/'scientific_seal.json'),
        protocol_sha256=sha(ROOT/'protocol.json'), verified_sealed_files=len(seal['files']),
        completed_fits=32, recomputed_gate_qualified_fits=accepted, matched_observation_pairs=16,
        maximum_error_norm_discrepancy_km=max_error,
        maximum_optimizer_minus_ELBO_offset_change=max_scalar_offset_change,
        maximum_score_decomposition_discrepancy=max_decomposition,
        wall_seconds_including_preparation_and_wait=execution['wall_seconds_since_first_preparation'],
        paired_summaries=[dict(intervention=k[0],arm=k[1],n=len(v),
            mean_error_km=float(np.mean([x for x,y in v])),control_mean_km=float(np.mean([y for x,y in v])),
            improved=sum(x<y for x,y in v),worsened=sum(x>y for x,y in v)) for k,v in sorted(groups.items())],
        position_fits=0,propagation=False,real_GPS_used=False,source_sha256=sha(Path(__file__)))
    with (HERE/'synthetic_terminal_audit.json').open('x') as handle:
        json.dump(output,handle,indent=2);handle.write('\n')
    print(json.dumps(output,indent=2))


if __name__ == '__main__':
    main()
