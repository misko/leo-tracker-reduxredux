"""Independent fixed-point construction audit; first-order adequacy is separate."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'scientific'))
import adapter
from gaussian_oracle import dense_nll, schur_factorization


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    def encode(v):
        if isinstance(v, np.ndarray): return v.tolist()
        if isinstance(v, np.generic): return v.item()
        raise TypeError(type(v).__name__)
    with Path(path).open('x') as stream:
        json.dump(value, stream, default=encode, indent=2, allow_nan=False)
        stream.write('\n')


def audit():
    adapter_hash = sha(adapter.__file__)
    rows = []
    for case in adapter.CASES:
        context = adapter.load_context(case)
        target_ids = context['target']['observation_ids']
        if len(target_ids) != len(set(target_ids)):
            raise ValueError('duplicate target IDs')
        for arm in adapter.ARMS:
            parent = context['parent_membership'][arm]
            if set(target_ids) & set(parent['curved_observation_ids']+parent['predictive_observation_ids']):
                raise ValueError('target double counted in parent')
            x = np.asarray(context['arms'][arm]['endpoint_east_north_km'])
            reference = np.asarray(context['arms'][arm]['phase_reference'])
            calculations, predictions = [], []
            for branch in adapter.BRANCHES:
                problem = adapter.build(context, arm, reference, branch)
                c = problem.calculate(x)
                pred = c['predictive_decomposition']
                direct = dense_nll(pred['raw_hz'], pred['covariance_hz2'])
                factored = schur_factorization(pred['raw_hz'], pred['covariance_hz2'], pred['parent_predictive_points'])
                error = max(abs(direct['negative_twice_log_density']-pred['joint']['objective']),
                    abs(direct['negative_twice_log_density']-factored))
                if error > 1e-6:
                    raise ValueError(f'Gaussian dense/factorization mismatch: {error}')
                radio_width = problem.hardware.shape[1]+problem.smooth.shape[1]
                if np.any(c['target_prediction']['shared_design'][:, radio_width:] != 0):
                    raise ValueError('target reuses parent phase/orbit/fragment coordinates')
                # Only target CFO changes; all source metadata and original priors stay fixed.
                changed = dict(context)
                changed['scan'] = copy.copy(context['scan'])
                changed['scan'].tracks = copy.deepcopy(context['scan'].tracks)
                i = context['target']['track_index']
                changed['target_track'] = changed['scan'].tracks[i]
                changed['target_track']['values'] = np.asarray(changed['target_track']['values'])+12345.
                redacted = adapter.build(changed, arm, reference, branch)
                after = redacted.calculate(x)
                for key in ('coefficient', 'noise_precision', 'coefficient_prior_precision'):
                    np.testing.assert_array_equal(c[key], after[key])
                np.testing.assert_array_equal(problem.reference, redacted.reference)
                np.testing.assert_array_equal(pred['posterior_precision'], after['predictive_decomposition']['posterior_precision'])
                np.testing.assert_array_equal(pred['covariance_hz2'], after['predictive_decomposition']['covariance_hz2'])
                np.testing.assert_allclose(after['target_raw_prediction_residual_hz']-c['target_raw_prediction_residual_hz'], 12345., atol=2e-10, rtol=0.)
                calculations.append(c)
                predictions.append(pred)
                rows.append(dict(case=case, arm=arm, branch=branch, dense_max_difference=error,
                    factorization_closure=pred['closure'], target_points=len(target_ids),
                    parent_predictive_points=pred['parent_predictive_points'],
                    target_redaction_parent_invariant=True, no_dormant_coordinate_reuse=True))
            zero, prior = predictions
            for key in ('raw_hz', 'sigma_hz', 'shared_design', 'posterior_precision'):
                np.testing.assert_array_equal(zero[key], prior[key])
            np.testing.assert_array_equal(calculations[0]['target_prediction']['mean_orbit_hz'],
                calculations[1]['target_prediction']['mean_orbit_hz'])
            n = zero['parent_predictive_points']
            shape = calculations[1]['target_prediction']['shape_columns_hz']
            increment = prior['covariance_hz2']-zero['covariance_hz2']
            expected = np.zeros_like(increment)
            expected[n:, n:] = shape@shape.T
            np.testing.assert_allclose(increment, expected, rtol=1e-10, atol=1e-6)
            np.testing.assert_array_equal(zero['covariance_hz2'][:n], prior['covariance_hz2'][:n])
            if np.linalg.eigvalsh(increment[n:, n:]).min() < -1e-6:
                raise ValueError('shape covariance increment not PSD')
            rows[-1].update(shape_increment_error=float(np.max(abs(increment-expected))),
                same_mean_noise_and_shared_prior=True)
            print('actual covariance audit', case, arm, 'pass', flush=True)
    if sha(adapter.__file__) != adapter_hash:
        raise ValueError('adapter changed during audit; do not reuse this result')
    result = dict(status='construction_pass', physical_phase_adequacy='FAIL; see phase_linearization.json',
        launch_approved=False, position_fits=0, GPS_used=False,
        source_sha256=sha(__file__), adapter=dict(path=adapter.__file__, sha256=adapter_hash), rows=rows,
        max_dense_difference=max(row['dense_max_difference'] for row in rows))
    write_new(HERE/'actual_gaussian_audit.json', result)


if __name__ == '__main__':
    audit()
