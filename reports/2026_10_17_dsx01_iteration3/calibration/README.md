# Training-only calibration checkpoint

This directory contains causal donor discovery, a training-only physical band
calibration bootstrap, and a nine-point prior-region portfolio. No production
file or sealed iteration-2 artifact changed. No RF was collected.

## Causal donor inventory

`donor_manifest.json` binds public `SharedFastScanStore.inputs`, `status` and
`plot_evidence` receipts: input/terminal/stage digests, radio serial, exact actual
RF/channel/receiver/edge mapping, sample rate, capture mode, both acquisition
generation tokens, capture start/end, and a conservative result-completion upper
bound. A donor's data end and complete status timestamp both precede target
start. Selection is nearest earlier acquisition among compatible proven results,
without using its position, satellite assignments, or the target calibration.

Generation tokens identify separate acquisitions; exact-token matching provides
zero donors. The declared arm matches the same `continuous-iio` stream family
and identical hardware/rate/mode/RF mapping, recording both tokens separately.
The status update is an upper bound on completion: later plot updates can exclude
an otherwise usable earlier result. Recorded RF mappings remain hypotheses.

| Target | Donor acquisition UTC | Acquisition age (h) | Donor high-minus-low offsets, internal RX0 / RX1 (Hz) |
|---|---|---:|---:|
| S01 | No proven available donor | — | Training-only paired fallback |
| S02 | 2026-10-16 20:00:57.763 | 1.009 | −15068 / +41636 |
| S03 | 2026-10-16 19:30:41.014 | 2.018 | −15206 / +44049 |
| S04 | 2026-10-16 21:01:30.998 | 1.009 | −15328 / +37126 |
| S05 | 2026-10-16 21:31:46.550 | 1.009 | −15388 / +41406 |

Only the two donor band differences initialize the new fit. The existing
zero-mean 50 kHz contrast prior is unchanged. Both current contrasts,
intercepts, slopes, clocks, timing, position and q remain free on training rows;
c is free or fixed zero according to the matched arm. A donor fit is not a
measurement of invariant hardware truth.

The no-donor initializer votes for a shared receiver band difference from
near-time low/high residual pairs, using the same eligible satellite column and
actual RF on both sides. A joint low/high histogram then proposes one common
receiver intercept/slope, requiring support in both bands. It does not subtract
independently chosen band modes. Every candidate remains eligible and every
training point remains in the unchanged point-mixture likelihood.

## Complete S03 development pilots

All eight receipts use the same early-to-late training/held split: 1994 points
each. Candidate membership is conditioned on the original complete-recording
discovery. No held CFO selects a seed, donor, geometry node or endpoint.

| Scope | Arm | Donor seed | Training assigned | Held assigned | Held RMS (Hz) | Free-fit KKT | Charged scores |
|---|---|---|---:|---:|---:|---:|---:|
| Neutral | fitted c | yes | 394 | 237 | 197.98 | 0.000162 | 364 |
| Neutral | fitted c | no | 420 | 237 | 194.81 | 0.000106 | 356 |
| Neutral | c=0 | yes | 386 | 248 | 201.35 | 0.000148 | 331 |
| Neutral | c=0 | no | 422 | 248 | 206.93 | 0.000033 | 351 |
| Nine points | fitted c | yes | 685 | 242 | 206.86 | 244.41 | 1000 |
| Nine points | fitted c | no | 536 | 226 | 203.03 | 97.56 | 1000 |
| Nine points | c=0 | yes | 710 | 225 | 202.06 | 291.94 | 1000 |
| Nine points | c=0 | no | 539 | 236 | 199.83 | 79.16 | 1000 |

Neutral fits have a 400-score/60-second cap and converge locally. Nine-point
fits have a 1000-score/120-second cap and all fail strict convergence. Their
elapsed inference time is about 11 seconds each. Nine exact proposal orbit
queries and nine seed-objective evaluations cover
`{−radius/2, 0, +radius/2}²` in the prior's east/north chart. Seeds are ranked by
training J only; the best three receive at most 200 refinement evaluations each,
then the best training state receives remaining polish. Each of 180 partial RX
density scores is conservatively charged as a whole objective evaluation, leaving
820 actual complete-objective calls including freeze closure. The grid uses no
absolute evaluation coordinates. Neutral and wide budgets differ, so their
difference does not isolate a geometry-policy effect at matched compute.

The donor has no held-count advantage in either matched neutral arm. The wide
donor arm gains 16 held assignments over its no-donor control with fitted c but
loses 11 with c=0. Overall held coverage remains 11.28–12.44%; training fit gains
do not establish predictive recovery. These negative pilots do not justify an
all-five run or tuning grid nodes from a configured location.

| Scope | Arm | Donor seed | Learned RX0 / RX1 offset (Hz) | RX0 / RX1 slope (Hz/s) | Configured reference distance (km) |
|---|---|---|---:|---:|---:|
| Neutral | fitted c | yes | −15041 / +44414 | +26.53 / +33.87 | 120.34 |
| Neutral | fitted c | no | −27683 / +26141 | +29.59 / +59.99 | 119.06 |
| Neutral | c=0 | yes | −15089 / +44334 | +27.73 / +33.43 | 120.56 |
| Neutral | c=0 | no | −27819 / +26059 | +29.26 / +59.09 | 118.34 |
| Nine points | fitted c | yes | −15441 / +45311 | +58.98 / −37.79 | 81.50 |
| Nine points | fitted c | no | −27860 / +24916 | −12.82 / +29.35 | 215.03 |
| Nine points | c=0 | yes | −15377 / +44595 | +58.66 / −42.07 | 79.10 |
| Nine points | c=0 | no | −27974 / +26003 | −19.03 / +28.82 | 228.35 |

Reference distances are evaluation-only distances to the operator-configured
station, not independently surveyed position errors. They never enter inference,
and a smaller distance or in-sample frequency fit does not establish better
localization. RMS uses a changing assigned population; all held points remain
in its coverage denominator. Full numerical fields are in `comparison.csv` and
`summary.json`; individual JSON/NPZ receipts preserve every completed pilot.

## Tests and next boundary

Seven component tests pass: held-CFO perturbation invariance through seed and
optimizer, unused donor-position invariance, paired fallback physics, exact
centered-to-raw correction/likelihood transport, c=0, conservative exact score
accounting, causal completion/end/hardware/RF checks, and prior-scaled grid
selection invariance. The free physical band columns are restored before
learning and frozen only after training with closure below 1e−7 Hz/objective.

No complete production cold pipeline was launched. The read-only
`production_replay_audit.md` identifies its public entry point, actual historical
costs, and the important distinction between old target-only temporal exclusions
and the current full-half test. The next production-component replay requires a
new generic full-half probe derivation and an explicit bounded allowance, not a
claim that these histogram initializers reproduce production discovery.
