# Cross-band shared-clock transfer does not improve held residuals

**Do not add either tested clock correction to geographic fitting.** Other RF
bands provide usable overlapping donors for 238 of 3,983 eligible target cases
across 62 of 72 scans. Both common fractional drift and common additive-Hz drift
worsen median paired held residuals on those targets, overall and in each dataset.
This is evidence against these particular conditional predictors, not proof
that physical receiver drift is absent.

| Dataset | Supported / eligible targets | Supported scans / 24 | Fractional wins | Fractional median paired gain, Hz | Additive wins | Additive median paired gain, Hz |
|---|---:|---:|---:|---:|---:|---:|
| DS7 | 103 / 1,346 | 22 | 49 / 103 | −1.73 | 49 / 103 | −3.62 |
| DS8 | 65 / 1,311 | 17 | 24 / 65 | −13.70 | 25 / 65 | −14.29 |
| DS9 | 70 / 1,326 | 23 | 28 / 70 | −12.20 | 29 / 70 | −9.63 |
| Total | 238 / 3,983 | 62 / 72 | 101 / 238 | −8.63 | 103 / 238 | −7.85 |

Positive gain means lower error. Each target contributes its median absolute
held residual; the table reports median paired differences against zero slope.
These are canonical 11.2-GHz frequency units, not position errors. Mean paired
gains are also adverse: −20.80 Hz fractional and −20.78 Hz additive. Remaining
targets use unchanged zero-slope fallback; across all 3,983 targets the median
gain is zero and mean gains are −1.243 and −1.242 Hz respectively.

## Physical hypotheses and fixed controls

The [protocol](PROTOCOL.md) preceded execution. This follows the
[exact-RF support diagnostic](../2026_09_29_contemporaneous_residual/README.md),
which had no qualifying same-RX targets. The new experiment requires different
RF from the target and preserves the temporal and candidate-diversity rules:
same scan; exclude target track and candidate number; at least 50% overlap of
the target training span; at least five donor training points spanning five
seconds inside that span; at least three distinct other candidate numbers.
Median within candidate number, then median across numbers. No requirement or
threshold was relaxed after observing outcomes.

The existing canonical observations scale native frequency by `11.2 GHz / RF`.
For **common fractional drift**, the donor canonical slope is transferred
unchanged. For **common additive native-Hz drift**, it is multiplied by
`donor RF / target RF` before aggregation. These are two explicit hypotheses;
dimensional compatibility is not evidence that either describes the hardware.
Every prediction uses the target's training-only time and residual means.

An opposite-RX, different-RF fractional predictor has 278 supported cases.
The fully matched comparison has 67 cases across 30 scans: same-RX fractional
improves 31/67, same-RX additive 33/67, and opposite-RX fractional 25/67.
Their respective median paired gains versus zero slope are −2.69, −2.51 and
−8.49 Hz. No tested arm improves the overall matched median. DS9's matched
subset improves for the same-RX arms, but its complete supported subset does
not; that subset result does not select a correction or override full accounting.

## Scope, verification and decision

All nine early/middle/late eight-scan panels are reused. Original bank support
was 4,328 tracks; 3,983 cases passed the earlier conditional residual export.
Case identities and residuals inherit the fitted positions, recording times
and candidate assignments. Candidate numbers are not independently verified
satellite identities. Interleaved training/held masks test prediction within
tracks, not causal forecasting, and cases/scans share fitted parameters.
This experiment does not establish statistical independence, isolated orbital
Doppler, calibrated clock drift, geographic improvement or new-site accuracy.

Three synthetic tests pass: RF scaling recovery; held-data/order isolation and
candidate exclusion with minimum diversity; and temporal support. The runner
verified the preceding experiment's source/input hashes before loading these
same exports. `results.json` binds the nine raw residual exports, protocol,
runner and reused scoring helpers with SHA-256. It retains every target,
predictor, donor number and donor RF. `coverage.json` records candidate-count
histograms before and after overlap/sample requirements for every panel and RX
arm. `summary.json` separates all targets, supported cases and matched cases.
Ruff lint and formatting pass. The run completed within its 90-second cap.

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest discover -s reports/2026_09_29_crossband_clock -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 90 .venv/bin/python reports/2026_09_29_crossband_clock/clock_transfer.py
```

No RF was collected, production code edited or geographic model refitted.
This closes the immediate same-scan donor-clock hypothesis without spending
on another unmotivated position fit. The earlier own-track slope improvement
cannot be reinterpreted as common receiver drift: it did not transfer reliably
from other candidate tracks here. Prioritize independent orbit/identity evidence
and checks of candidate-specific model errors before adding more unconstrained
clock parameters. Reliable short-window sub-km accuracy remains unresolved.
