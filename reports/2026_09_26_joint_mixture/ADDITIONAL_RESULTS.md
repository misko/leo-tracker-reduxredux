# Four additional DS5 scans: frozen joint model

Selected before new-model evaluation by fixed hash ranking, one per sample rate, excluding three original cases and two prior development examples. Model/core and calibration hashes match the original run. Locations and original masks remain reused: retrospective fixed-site evaluation, not fresh geographic validation.

| UTC | MS/s | Tracks | Sacramento error (km) | Reno error (km) |
|---|---:|---:|---:|---:|
| 09:00 | 2.5 | 20 | 18.50 | 42.65 |
| 11:20 | 7.5 | 56 | 5.79 | 5.00 |
| 12:20 | 10 | 46 | 6.72 | 5.00 |
| 12:40 | 5 | 41 | 6.72 | 9.41 |

## Joint assignment + clock predictive scores

Composite negative log predictive density per evaluation block; lower is better. Not RMS or a location probability.

| UTC | Noise (Hz) | Known location | Sacramento | Reno | Lowest score | Max chain score spread | Max assignment TV |
|---|---:|---:|---:|---:|---|---:|---:|
| 09:00 | 100.0 | 6.4126 | 6.3405 | 6.2464 | reno | 0.0108 | 1.000 |
| 09:00 | 200.0 | 6.4600 | 6.4747 | 6.4511 | reno | 0.0233 | 1.000 |
| 11:20 | 100.0 | 5.8906 | 5.9172 | 6.0081 | reference | 7.4765 | 1.000 |
| 11:20 | 200.0 | 6.3471 | 6.3513 | 6.3682 | reference | 0.0011 | 1.000 |
| 12:20 | 100.0 | 5.8709 | 5.9124 | 5.9182 | reference | 0.0005 | 0.125 |
| 12:20 | 200.0 | 6.3386 | 6.3451 | 6.3462 | reference | 0.0003 | 0.119 |
| 12:40 | 100.0 | 6.2619 | 5.9758 | 5.9891 | sacramento | 0.4197 | 1.000 |
| 12:40 | 200.0 | 6.4363 | 6.3804 | 6.3831 | sacramento | 0.4509 | 1.000 |

**Inference warning:** these are nominal combined-chain scores, not converged posterior results. At 11:20 / 100 Hz, reference and Sacramento chain scores differ dramatically and the location ordering changes by initialization. At 09:00 / 200 Hz, known-versus-Reno ordering also changes by chain. At 12:40, the reference chains disagree substantially at both noise settings. Equal pooling of nonconverged chains does not establish correct posterior mode weights; pooled predictive scores can be better than both chain totals because different tracks benefit from different modes. Do not interpret the following win counts as validated accuracy.

## Matched control comparisons

| Scope | Noise (Hz) | Model | Known beats Sacramento | Known beats Reno | Known lowest of three |
|---|---:|---|---:|---:|---:|
| Additional four | 100.0 | frozen_no_clock | 3/4 | 4/4 | 3/4 |
| Additional four | 100.0 | joint_no_clock | 2/4 | 2/4 | 2/4 |
| Additional four | 100.0 | joint | 2/4 | 2/4 | 2/4 |
| Additional four | 200.0 | frozen_no_clock | 3/4 | 4/4 | 3/4 |
| Additional four | 200.0 | joint_no_clock | 3/4 | 2/4 | 2/4 |
| Additional four | 200.0 | joint | 3/4 | 2/4 | 2/4 |
| All seven | 100.0 | frozen_no_clock | 4/7 | 7/7 | 4/7 |
| All seven | 100.0 | joint_no_clock | 4/7 | 5/7 | 4/7 |
| All seven | 100.0 | joint | 4/7 | 5/7 | 4/7 |
| All seven | 200.0 | frozen_no_clock | 4/7 | 7/7 | 4/7 |
| All seven | 200.0 | joint_no_clock | 5/7 | 5/7 | 4/7 |
| All seven | 200.0 | joint | 5/7 | 5/7 | 4/7 |

## Limits

The two chains can disagree on individual assignments; a favorable aggregate score is not convergence evidence. No inference settings or hyperparameters were changed to favor the added scans. The known location is not guaranteed to have the smallest score, especially against nearby estimates under an imperfect model. Numerical support remains ±120s, and dependence/GLRT calibration is unchanged.

Largest omitted historical timing prior mass among the added scans: 5.23%.
Largest posterior mean unexplained-track fraction in the added scans: 1.79%.

## Decision

Do not expand or deploy this sampler as-is. The frozen-ID timing-marginalized control favors the known location over Reno in all four additions (all seven total), versus only two of four additions (five of seven total) for the nominal joint scores. Fix posterior exploration and verify it on these bounded cases before attributing the ranking changes to the model or changing its priors/weights. The numerical core and historical calibration are unchanged; five tests pass, including the deterministic, score-independent scan-selection test.
