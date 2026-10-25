"""Independent actual residual/state audit, not phase-quadrature accuracy."""

import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import time

import numpy as np

import adapter as a
import quadrature02 as q
from matched_controls import measurement_binding

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COUNT = 81  # Construction identity only; the numerical rule is frozen elsewhere.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        assert os.environ.get(key) == '1'
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('180s independent fixed audit cap')))
    signal.alarm(180)
    began = time.monotonic()
    source = {str(path): sha(path) for path in [Path(__file__), Path(a.__file__), Path(q.__file__)]}
    rows = []
    for case in a.CASES:
        d = a.load_context(case)
        binding = measurement_binding(d)
        for arm in a.ARMS:
            saved = d['arms'][arm]
            x = np.asarray(saved['endpoint_east_north_km'])
            support = np.asarray(d['saved_support']['arms'][arm]['endpoint_east_north_km'])
            positions = [('baseline', x), ('support', support), ('midpoint', (x+support)/2), ('regional_start', np.zeros(2))]
            positions += [(f'baseline_axis_{axis}_{sign}', x+np.eye(2)[axis]*sign*.01) for axis in range(2) for sign in (-1, 1)]
            for branch in a.BRANCHES:
                p = q.build(d, arm, saved['phase_reference'], branch, COUNT)
                reference = np.asarray(p.reference).copy()
                # Cache immutability and exact repetition at a physical context.
                before = copy.deepcopy(p.original_parent_calculate(x))
                first, second = p.calculate(x), p.calculate(x)
                for field in ('negative_twice_elbo', 'normalization_constant', 'residual', 'coefficient', 'noise_precision', 'coefficient_prior_precision'):
                    np.testing.assert_array_equal(first[field], second[field])
                    np.testing.assert_array_equal(before[field], p.original_parent_calculate(x)[field])
                values = []
                for label, at in positions:
                    parent = p.original_parent_calculate(at)
                    calculated = p.calculate(at)
                    residual = p.residual(at)
                    target = calculated['nonlinear_target_prediction']
                    score = float(target['objective'])
                    np.testing.assert_array_equal(calculated['residual'][:-1], parent['residual'])
                    np.testing.assert_allclose(calculated['residual'][-1]**2, score, atol=1e-9, rtol=0)
                    np.testing.assert_array_equal(calculated['normalization_constant'], parent['normalization_constant'])
                    np.testing.assert_allclose(calculated['negative_twice_elbo'], parent['negative_twice_elbo']+score, atol=1e-9, rtol=0)
                    visibility = np.maximum(0, -parent['elevation'][p.keep])/2
                    np.testing.assert_array_equal(residual[:-len(visibility)], calculated['residual'])
                    np.testing.assert_array_equal(residual[-len(visibility):], visibility)
                    penalty = float(visibility@visibility)
                    volume = float(2*np.sum(d['powers'][p.noise_groups[p.keep]]*np.log(p.point_noise[p.keep]/40)))
                    expected = volume-float(parent['normalization_constant'])+penalty
                    scalar = float(residual@residual)
                    error = scalar-float(calculated['negative_twice_elbo'])-expected
                    assert abs(error) < 3e-8, (case, arm, branch, label, error)
                    for field in ('coefficient', 'noise_precision', 'coefficient_prior_precision'):
                        np.testing.assert_array_equal(calculated[field], parent[field])
                    values.append(dict(label=label, position_east_north_km=at.tolist(),
                        actual_optimizer_scalar=scalar, full_reported_objective=float(calculated['negative_twice_elbo']),
                        complete_target_conditional_NLL=score, parent_normalization_constant=float(parent['normalization_constant']),
                        fixed_noise_volume=volume, parent_visibility_penalty=penalty,
                        corrected_normalization_offset=scalar-float(calculated['negative_twice_elbo'])-penalty,
                        identity_error=error,
                        minimum_target_elevation_deg=min(target['minimum_node_elevation_deg'], target['minimum_domain_endpoint_elevation_deg'])))
                # Target-value redaction must not change any parent state.
                changed = dict(d)
                changed['scan'] = copy.copy(d['scan'])
                changed['scan'].tracks = list(d['scan'].tracks)
                index = d['target']['track_index']
                changed['target_track'] = dict(d['target_track'], values=np.asarray(d['target_track']['values'])+999.)
                changed['scan'].tracks[index] = changed['target_track']
                other = q.build(changed, arm, saved['phase_reference'], branch, COUNT)
                redacted = other.calculate(x)
                for field in ('coefficient', 'noise_precision', 'coefficient_prior_precision'):
                    np.testing.assert_array_equal(first[field], redacted[field])
                np.testing.assert_array_equal(p.state(x)['phases'], other.state(x)['phases'])
                np.testing.assert_array_equal(reference, p.reference)
                np.testing.assert_array_equal(reference, other.reference)
                assert first['parent_negative_twice_elbo'] == redacted['parent_negative_twice_elbo']
                assert first['nonlinear_target_prediction']['objective'] != redacted['nonlinear_target_prediction']['objective']
                assert d['target']['phase_mean_s'] == changed['target']['phase_mean_s']
                offsets = [v['corrected_normalization_offset'] for v in values]
                assert np.ptp(offsets) < 3e-8
                rows.append(dict(case=case, arm=arm, branch=branch, values=values,
                    target_redaction_preserves_parent_state=True, repeated_position_and_parent_cache_unchanged=True,
                    corrected_offset_spread=float(np.ptp(offsets))))
        assert measurement_binding(d) == binding, 'original parent scientific inputs mutated'
        print(case, 'nonlinear scalar, ownership and cache checks passed', flush=True)
    for path, digest in source.items():
        assert sha(path) == digest, 'source changed during independent audit'
    output = dict(all_passed=True, no_position_fits=True, GPS_used=False, quadrature_nodes_for_construction_test=COUNT,
        quadrature_accuracy_not_claimed=True, source_sha256=source, rows=rows,
        fixed_position_evaluations=sum(len(row['values']) for row in rows),
        maximum_scalar_identity_error=max(abs(v['identity_error']) for row in rows for v in row['values']),
        maximum_corrected_offset_spread=max(row['corrected_offset_spread'] for row in rows),
        minimum_target_phase_domain_elevation_deg=min(v['minimum_target_elevation_deg'] for row in rows for v in row['values']),
        full_target_NLL_added_exactly_once=True, target_NLL_normalization_not_added_twice=True,
        target_not_added_to_parent_entry_or_calibration_lists=True,
        operational_policy='saved_baseline', target_association_qualified=False,
        scientific_launch_approved=False, threads=1, seconds=time.monotonic()-began,
        caveat='81-node rule here tests construction identities only. Launch still requires the independently converged fixed rule, frozen budgets/source protocol and coordinator go.')
    with (HERE/'nonlinear_scalar_audit.json').open('x') as stream:
        json.dump(output, stream, indent=2); stream.write('\n')
    signal.alarm(0)
    print(json.dumps({k:v for k,v in output.items() if k not in ('rows','source_sha256')}, indent=2))


if __name__ == '__main__':
    run()
