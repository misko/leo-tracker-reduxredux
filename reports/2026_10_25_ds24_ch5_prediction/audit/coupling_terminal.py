"""Independent saved-matrix and fixed-gradient replay, without propagation."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.linalg import solve_triangular

HERE = Path(__file__).resolve().parent
SCI = HERE.parent / 'parent_coupling'
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    began = time.monotonic()
    output = HERE / 'coupling_terminal.json'
    if output.exists():
        raise FileExistsError('preserve terminal audit')
    checks = []

    def check(name, passed, **details):
        checks.append(dict(name=name, passed=bool(passed), **details))

    protocol, seal = read(SCI / 'protocol.json'), read(SCI / 'RF_seal.json')
    summary, result = read(SCI / 'summary.json'), read(SCI / 'results.json')
    bindings = dict(protocol['files']); bindings.update(seal['files'])
    check('all scientific/source/input hashes exact; matching preflight and protocol',
          all(sha(path) == digest for path, digest in bindings.items()) and
          seal['protocol_sha256'] == sha(SCI / 'protocol.json') == read(HERE / 'coupling_preflight.json')['protocol_sha256'])
    metadata = read(SCI / 'preparation.json')['rows']
    check('complete20 fixed probes and original300second cap',
          result['status'] == 'complete' and result['failure'] is None and len(result['rows']) == len(metadata) == 20 and
          result['cumulative_scientific_seconds'] <= 300 and result['position_fits'] == 0 and not result['GPS_used'])
    max_affine_error = max_proposal_error = 0.
    for row in metadata:
        name = row['case'] + '/' + row['arm'] + '/' + str(row['offset_km'])
        with np.load(row['artifact'], allow_pickle=False) as data:
            c = data['covariance'] + data['frozen_modes'] @ data['frozen_modes'].T
            root = np.linalg.cholesky(c)
            d = data['derivative']
            g = solve_triangular(root, d, lower=True)
            y = solve_triangular(root, data['raw'] - data['affine_intercept'], lower=True)
            variance = 1 / (1 / float(data['prior_sd']) ** 2 + g @ g)
            mean = variance * (float(data['prior_mean']) / float(data['prior_sd']) ** 2 + g @ y)
            cov = c + float(data['prior_sd']) ** 2 * np.outer(d, d)
            total_root = np.linalg.cholesky(cov)
            residual = solve_triangular(total_root,
                data['raw'] - data['affine_intercept'] - d * data['prior_mean'], lower=True)
            objective = float(residual @ residual + 2 * np.log(np.diag(total_root)).sum() + len(d) * np.log(2 * np.pi))
            affine_error = abs(objective - float(data['affine_conditional_objective']))
            proposal_error = max(abs(mean - float(data['proposal_mean'])), abs(np.sqrt(variance) - float(data['proposal_sd'])))
            max_affine_error, max_proposal_error = max(max_affine_error, affine_error), max(max_proposal_error, proposal_error)
            check('independent complete selected-family Gaussian/proposal replay: ' + name,
                  affine_error <= 1e-6 and proposal_error <= 1e-8 and
                  abs(float(data['full_gaussian_objective']) - float(data['other_gaussian_objective']) - objective) <= 1e-5 and
                  abs(float(data['prior_sd']) - row['original_phase_sigma_s'] / np.sqrt(row['original_phase_prior_precision'])) <= 1e-12,
                  affine_objective_error=affine_error, proposal_mean_or_SD_error_s=proposal_error)
            certificate = row['visibility_certificate']
            check('whole-family native IDs, exact original reference and full LOS: ' + name,
                  len(row['selected_native_IDs']) == len(d) and len(row['joint_native_IDs']) == len(set(row['joint_native_IDs'])) and
                  set(row['selected_native_IDs']) <= set(row['joint_native_IDs']) and
                  row['reference_B_error_hz'] <= 1e-7 and row['reference_frequency_error_hz'] <= 1e-7 and
                  certificate['inner_visible_intervals'] == [[-15., 15.]] and
                  not certificate['root_brackets'] and not certificate['unresolved_intervals'] and
                  sha(row['artifact']) == row['artifact_sha256'])
    replayed = []
    for selected in protocol['selections']:
        reported = next(row for row in summary['rows'] if row['case'] == selected['case'])
        for arm in protocol['arms']:
            rows = {row['offset_km']: row for row in result['rows'] if row['case'] == selected['case'] and row['arm'] == arm}
            delta = lambda h, rule: (rows[h]['adaptive_reference']['dynamic']['objective'] - rows[h]['adaptive_reference']['frozen']['objective']
                if rule == 'adaptive' else rows[h]['records']['dynamic'][rule]['objective'] - rows[h]['records']['frozen'][rule]['objective'])
            gradients = {rule: {h: (delta(h, rule) - delta(-h, rule)) / (2 * h) for h in (.025, .05)}
                         for rule in ('161', '321', 'adaptive')}
            score_error = max(abs(row['records'][branch]['321']['objective'] - other)
                for row in rows.values() for branch in ('frozen', 'dynamic')
                for other in (row['records'][branch]['161']['objective'], row['adaptive_reference'][branch]['objective']))
            gradient_error = max(abs(gradients['321'][h] - gradients[rule][h]) for h in (.025, .05) for rule in ('161', 'adaptive'))
            step_error = abs(gradients['321'][.025] - gradients['321'][.05])
            adaptive_error = max(row['adaptive_reference'][branch]['relative_error'] for row in rows.values() for branch in ('frozen', 'dynamic'))
            dense_error = max(row['maximum_dense_node_error'] for row in rows.values())
            gradient = gradients['321'][.025]
            qualified = (score_error <= 1e-3 and gradient_error <= 1e-3 and adaptive_error <= 1e-6 and dense_error <= 1e-5
                         and step_error <= max(.01, .05 * abs(gradient)))
            shift = -gradient / (2 * selected['weak_precision_per_km2'])
            uncertainty = max(gradient_error, step_error / 3, 1e-8) / (2 * selected['weak_precision_per_km2'])
            material = qualified and abs(shift) >= .025 and abs(shift) > 5 * uncertainty
            actual = next(row for row in reported['arms'] if row['arm'] == arm)
            check('independent gradients/qualification/materiality replay: ' + selected['case'] + '/' + arm,
                  qualified == actual['qualified'] and material == actual['material'] and
                  abs(shift - actual['weak_direction_displacement_proxy_km']) < 1e-12 and
                  abs(score_error - actual['maximum_score_disagreement']) < 1e-12 and
                  abs(gradient_error - actual['maximum_gradient_disagreement_per_km']) < 1e-12 and
                  actual['global_mode_certificate'] is False)
            replayed.append(dict(case=selected['case'], norad=selected['norad'], arm=arm,
                resolved=qualified, material=bool(material), signed_local_weak_movement_proxy_m=1000 * shift,
                numerical_agreement_proxy_m=1000 * uncertainty))
    check('restored stdout log is exact; emitted log preserved without scientific change',
          read(SCI / 'stdout_restoration.json')['RF_seal_unchanged'] and
          sha(SCI / 'execution.log') == seal['files'][str(SCI / 'execution.log')] and
          sha(SCI / 'execution_stdout.log') == read(SCI / 'stdout_restoration.json')['stdout_sha256'])
    check('no binding changed during artifact audit', all(sha(path) == digest for path, digest in bindings.items()))
    elapsed = time.monotonic() - began
    prior = read(HERE / 'coupling_preflight.json')['cumulative_audit_seconds']
    receipt = dict(all_passed=all(c['passed'] for c in checks), checks=checks, rows=replayed,
        maximum_independent_affine_objective_error=max_affine_error,
        maximum_independent_proposal_mean_or_SD_error_s=max_proposal_error,
        protocol_sha256=sha(SCI / 'protocol.json'), RF_seal_sha256=sha(SCI / 'RF_seal.json'), summary_sha256=sha(SCI / 'summary.json'),
        source_sha256=sha(__file__), seconds=elapsed, cumulative_audit_seconds=prior + elapsed,
        audit_cap_seconds=180, corpus_propagation_calls=0, position_fits=0, geographic_truth_read=False,
        conclusion='Both tested conditional neighborhoods have sub-metre local weak-direction effects. Close this specific frozen-Gamma/single-family/resolved-mode control; it is not a global hierarchy or position-accuracy result.')
    receipt['all_passed'] &= receipt['cumulative_audit_seconds'] <= 180
    output.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(path=str(output), all_passed=receipt['all_passed'], checks=len(checks),
        cumulative_audit_seconds=receipt['cumulative_audit_seconds'], rows=replayed,
        failed=[c for c in checks if not c['passed']])))


if __name__ == '__main__':
    main()
