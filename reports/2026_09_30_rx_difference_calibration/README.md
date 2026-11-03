# Paired RX difference scale predicts held disagreement on DS10

A training-only paired-RX scale feature, calibrated on DS7–DS9, improves held RX-difference likelihood on **all 24 DS10 scans**. The equal-scan mean gain is **+0.063693 nats per held paired observation** over a constant-scale Student-t4 model. This is a promising uncertainty diagnostic, **not calibrated absolute Doppler uncertainty or a geographic accuracy improvement**.

| Quantity | Result |
|---|---:|
| Donor datasets / scans | DS7–DS9 / 72 |
| Donor track pairs / held paired observations | 953 / 17,888 |
| Target dataset / scans | DS10 / 24 |
| Target track pairs / held paired observations | 355 / 7,195 |
| Target scans with positive mean log-score gain | 24/24 |
| Equal-target-scan mean log-score gain | +0.063693 nats |
| Minimum / maximum scan gain | +0.007823 / +0.197124 nats |
| Constant fitted t4 scale | 98.053 Hz |
| Fitted log-feature exponent | 0.642338 |
| Runtime | 4.08 s |

![Calibration transfer and scale model](calibration.png)

The variable model is `scale = exp(1.631307) × feature^0.642338`, with numerical feature and scale values expressed in Hz. Its parameters use no DS10 outcomes. The feature is `max(1 Hz, 1.4826 × training MAD)` of the RX0-minus-RX1 residual difference after subtracting its training median. Scale is a Student-t distribution parameter, not a standard deviation or confidence bound.

## Pairing and coverage

| Dataset | Candidate track pairs considered | Pairs passing timing/mask/support rules | Held paired observations |
|---|---:|---:|---:|
| DS7 | 516 | 326 | 6,317 |
| DS8 | 498 | 317 | 5,694 |
| DS9 | 493 | 310 | 5,877 |
| DS10 | 471 | 355 | 7,195 |

Tracks share a scan, exact RF and a training-selected candidate hypothesis. Observation pairing uses mutual nearest timestamps within one microsecond. This tolerance was set after inspecting timestamp coverage, before evaluating calibration outcomes. Exact timestamp equality misses many paired observations because RX times differ at sub-microsecond precision.

At least eight both-training pairs spanning five seconds and three both-held pairs are required. Mixed-mask observations are excluded. Each accepted track pair supplies a training-only median offset and scale feature. Held centered differences are scored without adjusting either. Scan-local catalogue indices in DS10 are compared only within that scan; this does not establish actual satellite identity.

The donor fits use equal dataset weights, equal scan weights within each donor dataset and equal observation weights within each scan. The final score averages DS10 scan means equally. Track pairs may share observations across alternative tracks; correlated pairs and repeated observations are not independent trials, and 24/24 signs are not an iid significance calculation.

## Meaning for the sub-km effort

The scale of RX disagreement is predictable across datasets. This offers a better-supported starting point for uncertainty modeling than treating detector margin as a precision estimate, which showed mixed transfer in the [earlier calibration test](../2026_09_29_margin_calibration/README.md). These are different targets and populations, so their score gains are not a head-to-head comparison.

Crucially, a shared additive error cancels in an RX difference. Low difference variance can coexist with a large common frequency error, incorrect shared association, or incorrect geographic solution. The individual RX variances and their covariance cannot be recovered from this difference alone. Do not divide the fitted scale by sqrt(2) and treat it as a calibrated per-RX uncertainty without additional evidence.

The next discriminating test is whether this feature predicts each receiver's held frequency innovations or the common part of their errors on the same pairs, with calibration frozen on DS7–DS9. If it predicts only disagreement, retain it as a differential-noise diagnostic. Only evidence of useful individual-observation uncertainty would warrant a bounded geographic weighting experiment. No position-information-removing slope correction was introduced here.

## Verification and limitations

Both calibrations pass optimizer success, interior parameter, gradient <=1e−5 and finite-difference gradient-audit <=1e−5 gates. Maximum fitted gradient is 7.76e−9; maximum audit discrepancy is 1.17e−9. Three component-owned tests pass: shared-signal cancellation, held-value isolation and analytic likelihood-gradient agreement. Input/source digests verify. [results.json](results.json) preserves paired errors, features, coverage, fitted parameters and hashes; [summary.json](summary.json) includes all scan scores.

The [protocol](PROTOCOL.md) preceded calibration. The residual exports and assignments depend on earlier geography fits using both receivers' training data, and all datasets have prior research exposure. This is conditional exploratory transfer, not blind navigation validation. No new RF collection, propagation, exports, geographic fits, production changes or remote publication occurred.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_30_rx_difference_calibration -p 'test_*.py'
cd reports/2026_09_30_rx_difference_calibration
sha256sum -c evidence.sha256
```
