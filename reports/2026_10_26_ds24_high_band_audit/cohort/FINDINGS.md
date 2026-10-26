# Saved DS24 high-band cohort audit

The high-band localization deficit is tail-heavy, with evidence of different mechanisms in the main tail cases. The saved residuals do not support explaining the deficit as a uniform high-band frequency-noise penalty, one fixed spatial offset, or widespread replacement of one accepted model identity by another. Reduced support, receiver-dependent correlated discrepancy, coherent position/timing/calibration tradeoffs, and case-specific accepted-family membership all remain relevant.

This audit reads the original 24 matched scans only. It performs no new position, nuisance, association, geometry, detector, or raw-IQ analysis. The only regressions are descriptive slopes of already saved conditional CFO residuals. The controlled `c=0` and fitted-`c` arms remain separate throughout. Satellite/NORAD labels below are model assignments, not independently established emitter identities.

## Paired distribution and the c control

| Saved arm | Mean low error | Mean high error | Mean high–low gap | Median paired gap | High worse | Top two paired deficits' share of net gap |
|---|---:|---:|---:|---:|---:|---:|
| c=0 | 1.538 km | 2.040 km | +0.502 km | +0.278 km | 15/24 | 63.8% |
| fitted c | 1.558 km | 2.040 km | +0.483 km | +0.151 km | 14/24 | 64.6% |

The largest fitted-c paired deficits are DS24-0015 (+4.942 km), DS24-0019 (+2.538 km), and DS24-0097 (+2.240 km). Removing 0015 and 0019 leaves a mean paired deficit of +0.187 km; the high band is not consistently worse on every scan. 0097 is second-worst in absolute high-band error, but third-largest in paired deficit.

Fitting c changes mean position error by +19.8 m low, +0.6 m high, and +17.9 m full, while reducing mean curved CFO RMS by only 0.045, 0.043, and 0.036 Hz respectively. These saved controlled comparisons provide no cohort localization advantage from fitting c. The high-band deficit already exists at c=0.

The raw mean scan RMS is 67.024 Hz low versus 75.711 Hz high. At the same 11.5 GHz reference it is 68.913 versus 71.570 Hz, a 3.86% difference. The raw-Hz difference cannot be interpreted as the same-sized difference in angular/Doppler accuracy.

## Most of the count deficit starts before localization

| Stage, all 24 scans | CH1–4 | CH5–8 |
|---|---:|---:|
| Original GLRT observations | 60,059 | 48,541 |
| Graph observations | 54,186 | 43,241 |
| Raw-curvature graph observations | 39,954 | 32,326 |
| Final active curved observations | 37,262 | 29,553 |
| Additional predictive observations | 5,359 | 3,786 |
| Raw-curvature / GLRT | 66.52% | 66.60% |
| Final curved / raw-curvature | 93.26% | 91.42% |
| Final curved / GLRT | 62.04% | 60.88% |

The high band begins with 19.2% fewer GLRT observations and ends with 20.7% fewer active curved observations. Its graph/GLRT retention is 89.08% versus 90.22% low. There is modest extra attrition after raw curvature, but no cohort collapse at the raw-curvature stage. Raw curvature exactly reuses the existing descriptive rule: span at least 20 s and linear-detrended RMS at least 250 Hz. A causal fixed-Hz-gate effect has not been tested here.

Median active-family counts are 18 low versus 16 high, and median per-scan median track spans are 34.73 versus 36.33 s. The high band does not simply have shorter retained tracks. Paired error-gap correlations with differences in curved points, family counts, and track spans are only +0.060, −0.089, and −0.020 in fitted c. These small-cohort descriptive correlations do not turn point or family counts into geometric information.

0015 has 1,599 raw-curvature high points and 1,379 active points (86.24%), versus 1,829 and 1,725 low (94.31%). 0097 has 1,048 and 876 high (83.59%), versus 1,778 and 1,743 low (98.03%). 0019 has similar retention fractions high/low (88.61%/89.71%). The focus scans span approximately 295–299 s in both halves. The evidence is not a missing whole scan segment.

## Receiver structure is stronger than the normalized band contrast

For the separate half-band fitted-c fits, medians of per-scan conditional RMS normalized to 11.5 GHz are:

| Receiver | CH1–4 | CH5–8 |
|---|---:|---:|
| RX1 | 83.36 Hz | 81.20 Hz |
| RX2 | 33.48 Hz | 34.25 Hz |

RX1 supplies a mean 59.0% of active curved points in low-only fits and 62.3% in high-only fits. A pooled raw RMS mixes this support composition with RF scaling and heterogeneous receiver scatter.

The saved full-fit nearest-measured-time correlation audit is particularly informative. For same-RX/same-band lanes assigned to different families, fitted-c median correlations are +0.512 RX1 low, +0.507 RX1 high, +0.005 RX2 low, and +0.024 RX2 high. Per-scan median correlations give the same split (approximately +0.484 RX1 in both bands; +0.010/+0.028 RX2). c=0 is similar. These dependent conditional residual correlations favor investigating a receiver/shared-model discrepancy, but do not identify a hardware cause or establish TLE correctness.

No simple remaining linear residual drift explains the three tail cases: pooled within-family/RX/channel slopes are small, and explain at most 0.03% of centered conditional residual sum-of-squares for those cases. The model has already fitted drift and smooth terms; small remaining residual drift is not evidence that fitted drift/calibration is physically correct.

## Timing and calibration changes are scan dependent

The mean high-minus-low endpoint vector is [+0.267 east, +0.495 north] km. Its length is 0.562 km, versus 2.638 km RMS dispersion around that mean (component SDs 1.729 and 1.992 km). This is poor evidence for one fixed spatial correction.

In 0015, all 15 shared high/full active curved families shift toward a positive timing change; the median signed shift is +0.571 s. Major families include 66426 (353 high points, +0.631 s), 66543 (160, +0.579), 67848 (136, +0.571), and 67829 (133, +0.576). In 0097 all 15 shared families shift positive, +0.262 to +0.440 s, median +0.335 s. This coherent family behavior is consistent with a shared timing/position/calibration tradeoff, not an isolated family residual problem.

Saved high-band receiver drift coefficients, decoded as `state.beta[4+lane]/150` Hz/s, also move materially. 0019 high-only RX1/RX2 are −0.078/+2.572 Hz/s versus +3.702/+3.908 in the full fit's high band; 0097 gives −2.981/−0.823 versus −0.350/+0.446. These are prior-coupled estimates under different support, not separately identified hardware drifts.

No saved reference in this cohort reaches the ±15 s relinearization clip. The largest high-only fitted-c active phase magnitude is 14.087 s; the focus cases' maxima are 5.337, 9.688, and 2.822 s. Every high endpoint is at least 2.236 km from the nearest ±12.5 km coordinate-box edge. The largest available high fitted-c final phase change is 0.000527 s. The evidence does not point to clipping or an unconverged final phase round as the general explanation.

## 0019 has a specific family-membership difference and a saved alternative

High-only 0019 retains family 48323 on 119 curved RX1 CH5/6/8 observations at 0–49 s, plus 21 predictive CH7 observations. Its fitted phase is +9.688 s against a stored prior mean of 0 s. It also retains family 57371 on 26 curved RX1 CH6 observations at 1–26 s, with phase +9.111 s against mean −0.102 s.

All 166 exact high likelihood observation IDs are present in the full input and unassociated in the final full fit, for both c controls. They are not assigned to competing identities in the full fit. Full `result.json` initially includes all four 48323 curved tracks (including CH4, 52 points), plus 57371. Full `algo02_result.json` records all four 48323 tracks removed at curved-history gate epoch 0 and 57371 removed at epoch 1. Low removes the CH4 48323 track at epoch 0. High retains the early high-band tracks and removes other CH8 tracks instead. The saved final surviving gates do not preserve the specific failed statistic from those removed rounds.

The saved cavity search already tested 48323→67338. That alternative is paired-valid and has evaluation errors 2.02955 km c=0 and 2.03442 km fitted c, versus approximately 3.17 km for the retained high-only solution. However, its negative-twice-ELBO is worse by +3.846071 (c=0) and +3.759728 (fitted c). The saved adoption policy therefore correctly rejects it under its equal-assignment-prior objective; recorded selection gain is −3.846071 and search penalty 20.755029. The alternative was not entirely missed. The smaller geographic error is post-hoc evaluation and cannot justify selecting that identity. The 57371→67338 trial and the joint replacement both fail paired validity.

This case demonstrates uncertainty in model preference and accepted-family support. It does not establish whether 48323 or 67338 is the physical emitter. Historical seed `compatible=False` and `feasible_candidates=0` fields persist even for later recovered tracks; they are not final ambiguity or rejection diagnostics.

## Reproduction and limits

Run `audit.py` and `audit_0019_membership.py` with the repository's `.venv/bin/python`. All outputs stay in this directory. `provenance.json` records input and script SHA256 hashes. `0019_membership_history.json` records exact mask/history membership; `0019_saved_alternatives_excerpt.json` copies the relevant saved trial fields with source JSON pointers and SHA256, and separates derived evaluation values.

`audit.py` reconstructs all 144 saved scan/group/arm conditional RMS values and their RF-normalized values from 265,850 saved point residual records, within 1e-6 Hz. It verifies graph/raw-curvature counts, RF identity by observation ID, and curved-plus-predictive count fallback. Full-fit local band information is read as an existing conditional diagnostic, not recomputed or represented as calibrated half-fit confidence.

Useful figures are `paired_cohort.png`/`.pdf`, `focus_phase_shifts.png`, and `focus_residual_time.png`. The residual-time bins mix changing family support and are descriptive. `scan_metrics.csv`, `paired_scans.csv`, `family_metrics.csv`, and `residual_lanes.csv` preserve per-case numerical detail. No production source, golden fixture, persisted scientific input, or RF corpus was changed.
