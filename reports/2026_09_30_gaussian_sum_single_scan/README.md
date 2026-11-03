# Gaussian-sum single-scan localization: first experiment

**Decision: stop before panel expansion.** The prototype is implemented and its
independent numerical tests pass, but the first DS9 replay does not support
promoting the bounded Gaussian mixture. At the eighteenth completed track,
retaining 16 components discards **13.01%** of posterior probability, above the
predeclared 1% limit. The broader prior also leaves supported orbit times.
Neither failed result is an accepted location estimate.

This executes the preparation, prototype, implementation, and first-scan gates of
the [plan](../../plans/gaussian-mixture-single-scan-localization.md). All 48 selected
DS9/DS10/DS11 inputs were audited; only DS9-F001 was fitted. The other 47 scans
remain unstarted behind the scientific gate. There are no DS10/DS11 accuracy
results from this experiment, and repeated arms/retries are not independent scans.

## What is implemented

The [pure analyzer](../../src/leo/analysis/gaussian_sum_location.py) branches each
location component over satellite identity and background, scores normalized
predictive likelihoods, conditions continuous states, and normalizes globally.
Position, height, UTC offset, shared receiver drift, and shared per-satellite epoch
uncertainty remain in the joint Gaussian state across tracks. Track-local constant
frequency offsets are removed by orthonormal contrasts. Duplicate observations
are rejected and all pruning is accounted for explicitly.

The [physics adapter](physics.py) uses WGS84 receiver positions, propagated ECEF
states, Hermite position interpolation, independently interpolated authoritative
velocities, and Doppler at the export's verified **11.2 GHz canonical frequency**.
Physical receiver drift is converted from each track's actual RF frequency.
Candidate selection uses a conservative geometric bound over the declared region,
without measured residuals or previous satellite winners. The older response-picked
shortlists were rejected for this experiment.

Three concurrent SOL workers owned evidence, inference, and independent
verification. The coordinator froze interfaces and protocols, integrated the
runner, and made the recorded advance/repair/stop decisions. No new RF collection,
raw-IQ processing, golden-fixture edits, or remote publication occurred.

## Inputs and evidence limits

The frozen panel contains 8 DS9, 8 DS10, and 32 DS11 scans, with verified source,
inventory, and manifest bindings for all 48. Exact IDs are in [selection.json](selection.json).
The deterministic overlap audit is in [data-audit.json](data-audit.json).

| Dataset | Scans audited | Exported tracks | Retained tracks | Excluded tracks |
| --- | ---: | ---: | ---: | ---: |
| DS9 | 8 | 472 | 359 | 113 |
| DS10 | 8 | 478 | 358 | 120 |
| DS11 | 32 | 1,923 | 1,446 | 477 |

Original detector observation IDs and covariance are unavailable in these exports.
The adapter conservatively identifies observations by session/RX/channel/visit,
then excludes later overlapping tracks. This can discard independent signals.
Aliases and discontinuities are not recoverable from the exported metadata.
These are completed-track retrospective replays, not demonstrated causal online
detections or future-RF forecasts.

The smoke scan is `scan-fw-98cb28475c2059b9` (DS9-F001). Its archived catalogue
predates capture by 4,424 seconds. Of 11,130 catalogue objects, 11,129 propagate;
NORAD 100560 fails and the receipt records a catalogue gap. The conservative
regional/time union admits 994 candidates. Of 64 exported tracks, 50 survive the
overlap rule. At most eight time-spread samples per track enter each factor.

## Frozen retry results

The [protocol](PROTOCOL.md) and [amendment](AMENDMENTS.md) distinguish the original
implementation from its numerical retry. Version 1 failed on negligible branches
outside interpolation support; its greedy baseline hit the time budget. Version 2
uses a 1e-12 posterior weight floor and vectorized prediction. All discarded mass
is still reported, and the 1% gate, physical model, priors, evidence, and budgets
remain unchanged. Original receipts and source snapshots are preserved.

| v2 arm / prior | Factors consumed | Native status | Wall time | Interpretation |
| --- | ---: | --- | ---: | --- |
| Gaussian sum / regional | 18 of 50 | gate_failed | 18.79 s | 13.01% mass discarded at factor 17; stop |
| Greedy / regional | 50 of 50 | complete | 4.69 s | Completed conditional baseline; commits to one lineage |
| Prior only / regional | 0 | complete | 0.24 s | No RF update |
| Gaussian sum / broad stress | 4 of 50 | error | 5.68 s | A retained time offset exceeds four-knot orbit support |

Factor indices in receipts are zero based. The stress run was already launched
within the first-scan test when the regional gate failed; it completed before any
panel expansion. No further scientific fits were launched.

The prediction-only benchmark across all 994 candidates improved from 5.963 s to
0.0724 s per parent (82.4x). Compared with the preserved scalar implementation,
the largest predicted-frequency difference was 1.51e-10 Hz, the largest Jacobian
difference 7.96e-7, covariance was identical, and eligibility never changed. This
is an implementation benchmark, not an accuracy improvement.

Sealed predictions, progress records, full nuisance states, and launcher commands
are under [runs/v1](runs/v1) and [runs/v2](runs/v2). Launcher completion denotes
process completion: scientific acceptance requires reading the native prediction
status. [panel-accounting.json](panel-accounting.json) accounts for attempts and
unstarted work; [evaluation.json](evaluation.json) keeps failures in its denominator.

## Interpretation and next design

The regional filter preserves several plausible hypotheses initially. The failure
occurs when association histories branch faster than the 16-component representation
can retain them. Increasing confidence by renormalizing the surviving 87% would
hide a material approximation. A useful next experiment should test probability-
preserving Gaussian reduction, merging only sufficiently similar joint states and
including between-component covariance, against a small exact mixture or grid.
It must preserve separated geographic modes and shared nuisance uncertainty.

The stress failure needs explicit treatment of orbit-time support and broad-prior
nonlinearity. Do not clamp time offsets or extrapolate the orbit silently. Audit
the retained branches and choose a bounded support/relinearization design before
running a revised experiment. In this run, just one retained component, with
weight 3.13e-12, queries 0.869 seconds beyond support. More than
0.9999999999968 of saved mass has supported center queries. This is a coverage-
handling defect, not evidence that the broad prior cannot locate the receiver.
An explicit support-abstention branch would preserve that missing probability.

The background slope prior has SD 100 Hz/s, whereas the first observed track spans
40,357 Hz in 11.53 seconds, roughly -3,499 Hz/s. Its background probability is
about 6e-262. The density is normalized but this engineering prior can strongly
favor an in-catalogue explanation. Noise covariance, background behavior, other
orbit errors, and location-dependent detection probabilities require development
validation. No NORAD identity truth is available. Antenna roll and an assumed
rectangular LNB field of view are not fitted in this prototype.

Location regions are conditional diagnostics. The inherited prior center already
has historical development exposure; the roof reference is operator supplied and
unsurveyed. Evaluation includes the unchanged center and mixture-mean controls,
so a poor arbitrarily tie-broken prior mode cannot create an artificial claim of
RF improvement. One roof recording cannot establish calibration or transfer.

The completed greedy baseline is **0.518 km** from the roof reference, compared
with **0.809 km** for the unchanged configured center / prior mixture mean.
That 0.291 km descriptive improvement is encouraging, but comes from a single
recording with an assumed likelihood and committed satellite identities. It does
not validate the failed Gaussian-sum output or establish navigation accuracy.

## Figures

The [figure notes](figures/README.md) distinguish matched-support comparisons,
the completed greedy baseline, and rejected Gaussian-sum diagnostics.

![Prior and first update](figures/DS9-F001-regional-gaussian_sum-first-density.png)

![Association and retained probability](figures/DS9-F001-regional-gaussian_sum-association-mass.png)

![Location mixtures at matched support](figures/DS9-F001-regional-matched-location-density.png)

## Verification and reproduction

**58 tests passed** in the final combined run (1.64 seconds).

Independent tests cover exact joint-Gaussian conditioning, sequential/batch
agreement, mixture normalization and ambiguity recovery, a 24,001-point 1D grid
oracle, shared errors, duplicate rejection, source-prior conservation, extreme
likelihoods, deterministic prefixes, physical derivatives and interpolation,
candidate coverage, support gates, source bindings, and launcher failures/timeouts.
The synthetic coverage smoke contained truth in 75 of 80 trials (93.75%); this is
not real-data calibration or a two-dimensional geographic validation.

Run the bounded tests from the repository root:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src .venv/bin/python -m pytest -q tests/analysis/test_gaussian_sum_location.py reports/2026_09_30_gaussian_sum_single_scan/test_*.py
```

To reproduce the current regional smoke into a **new** output directory:

```bash
.venv/bin/python reports/2026_09_30_gaussian_sum_single_scan/launch.py DS9-F001 gaussian_sum --prior regional --output reports/2026_09_30_gaussian_sum_single_scan/runs/reproduction
```

The launcher enforces 90 seconds and one numerical thread; the runner enforces a
6 GiB address-space limit. Saved outputs are never overwritten. External source
observations and archived TLEs must still exist at their hash-bound local paths.
The analyzer has no dependency on either reference repository, storage, HTTP,
CLI, or the evaluator. The experiment tools remain private research interfaces.
