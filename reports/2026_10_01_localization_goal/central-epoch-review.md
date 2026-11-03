# Matched central-curvature timing prior

Reject expansion of this pilot: the Student timing prior improves the difficult DS10 scan but worsens both other development scans. Numerical convergence is successful, so these regressions cannot be dismissed as failed optimization.

| Scan | Original Gaussian error (m) | Student error (m) | Student wall time (s) | Student CPU time (s) |
| --- | ---: | ---: | ---: | ---: |
| DS9-F025 | 2,223.70 | 3,155.49 | 2.287 | 2.209 |
| DS10-F028 | 7,733.56 | 4,627.94 | 2.001 | 1.979 |
| DS11-F018 | 1,257.18 | 1,352.92 | 1.629 | 1.609 |

Candidate acceptance is 3/3; 0/3 are within 1,000 m and 1/3 within 3,000 m. Candidate median error is 3,155.49 m and p90 is 4,333.45 m. These are three exposed development scans, not the 64-scan benchmark. Times cover warm fitting and preparation, excluding acquisition. No uncertainty coverage or held-out evaluation was performed.

## Model

The original Gaussian epoch penalty is `2 e²`, with variance 0.25 s² and central curvature 4 s⁻². The candidate uses a normalized Student-t4 prior with scale squared 5/16 s² and variance 5/8 s². Its variable penalty is `2.5 log(1 + e²/1.25)`, gradient `5e/(1.25 + e²)`, and central curvature also 4 s⁻². Gaussian normalization constants are subtracted when replacing priors to preserve the existing objective convention. Fitted objectives from different models are not used to select a geographic winner.

This deliberately changes variance and tail shrinkage while preserving curvature at zero. It differs from the earlier variance-matched Student prior, whose central curvature was 10 s⁻². Thus the prior experiment's increased central shrinkage does not explain all of the inconsistent geographic transfer: this matched-curvature version still fails two of three comparisons.

Both arms start at the same sealed original baseline state and use its fixed hard assignments, original observations, uniform Sacramento support, fixed 30.48 m MSL height, shared clock and receiver drift priors. The bounded scaled BFGS solver jointly optimizes position and active nuisance coordinates. Limits remain 64 iterations, 25 s internal, 30 s external, and at most two fitting processes. The estimator does not read reference coordinates. Its model hypothesis was informed by previously exposed development diagnostics.

## Verification and decision

Two prior tests passed: central curvature and finite-difference derivatives including tails; density normalization and variance by transformed numerical quadrature. All six control/candidate outcomes passed source/input/height/assignment seals, support, unchanged unused coordinates, reconstructed objectives and metrics, monotone descent, and full-coordinate finite-difference stationarity. All Gaussian controls recover the original state without a step. Candidate fits take 6–15 iterations. Maximum gradient discrepancy is 3.17e-5, and maximum numerical scaled decrement squared is 2.34e-7. Geographic scoring follows all numerical acceptance decisions; failed runs would remain in the denominator.

Receipts and source freeze are in `central-epoch-v1/`; `central-epoch-v1-evaluation.json` and its SHA seal are authoritative. Research adapter: `central_epoch_pilot.py`; batch: `central_epoch_batch.py`; evaluator: `evaluate_central_epoch.py`; tests: `test_central_epoch_prior.py`. No production component or golden fixture changed.

Do not expand this prior or sweep its scale against exposed geographic errors. The full baseline remains 2,059.90 m median and 5,850.75 m p90 with 64/64 acceptance. The goal remains unmet.

Before another flexible likelihood, inspect how measured carrier frequency is normalized into Doppler across channels. Trace track RF metadata and the canonical-frequency conversion through acquisition and final fitting, then quantify sensitivity to any supported carrier-frequency uncertainty at sealed states. This is a bounded physical-model audit, not permission to fit arbitrary frequency scale or tune it to GPS. Review existing frequency-related reports first to avoid repeating an already rejected model.
