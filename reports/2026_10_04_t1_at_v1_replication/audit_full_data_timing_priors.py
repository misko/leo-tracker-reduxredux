"""Verify on every real scan that ONLY timing regularization was changed."""
import json

import numpy as np

import full_data_timing_priors as experiment
from subset_positions import serial


def main():
    checks = []
    for scan in experiment.SCANS:
        data, saved, _ = experiment.load(scan)
        for arm in experiment.ARMS:
            baseline = experiment.objective(data, saved, arm, 'baseline')
            vector = np.asarray(saved['arms'][arm]['best']['vector'])
            value, gradient = baseline.evaluate(vector)
            penalty, prior_gradient = baseline.base.penalty(vector[:baseline.size])
            prior_gradient = np.r_[prior_gradient, 0.]
            raw_hessian = baseline.curvature(vector)
            for mode, precision in experiment.PRECISIONS.items():
                obj = experiment.objective(data, saved, arm, mode)
                other, other_gradient = obj.evaluate(vector)
                expected_value = value+(precision-1)*penalty
                expected_gradient = gradient+(precision-1)*prior_gradient
                np.testing.assert_allclose(other, expected_value, atol=1e-7, rtol=0)
                np.testing.assert_allclose(other_gradient, expected_gradient, atol=1e-7, rtol=0)
                expected_hessian = raw_hessian.copy()
                expected_hessian[6, 6] += (precision-1)*.01
                indices = np.arange(7, obj.size)
                expected_hessian[indices, indices] += precision-1
                actual_hessian = obj.curvature(vector)
                np.testing.assert_allclose(actual_hessian, expected_hessian, atol=1e-7, rtol=1e-14)
                assert obj.bounds == baseline.bounds
                assert obj.base.minimum_shift_s == baseline.base.minimum_shift_s
                assert obj.base.maximum_shift_s == baseline.base.maximum_shift_s
                checks.append(dict(scan=scan, arm=arm, mode=mode,
                    objective_difference_error=float(abs(other-expected_value)),
                    maximum_gradient_error=float(np.max(abs(other_gradient-expected_gradient))),
                    maximum_fisher_error=float(np.max(abs(actual_hessian-expected_hessian)))))
    out = dict(passed=True, checks=checks, cases=len(checks),
               assertion='Identical data likelihood, gradients, Fisher curvature and support; only timing-prior precision changes.')
    (experiment.OUT/'prior-isolation-audit.json').write_text(json.dumps(out, default=serial, indent=2, allow_nan=False))
    print('PASS: objective, gradient, curvature and bounds isolated in', len(checks), 'real-scan cases')


if __name__ == '__main__':
    main()
