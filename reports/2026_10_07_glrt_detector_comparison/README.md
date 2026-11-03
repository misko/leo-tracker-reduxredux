# GLRT versus standard detector alternatives

Completed October 7, 2026 using three SOL workers and independent integration
review. **Keep the current production detector.** The prototypes confirm that
GLRT is a reasonable approach and identify useful model-dependent alternatives,
but this bounded real-IQ comparison does not establish a replacement.

The most promising follow-up is covariance-aware scoring with representative,
independent background training. Shorter coherent segments merit consideration
when phase stability is demonstrably poor. Changing the current score's
normalization alone does not improve its same-candidate frequency estimate.

## Implemented and tested

The research-only [scorer](methods.py) implements:

| Method | Statistic and purpose |
|---|---|
| Current GLRT64 margin | Existing coherent-ceiling exact score minus independently maximized rolled-template control score. |
| Gaussian GLRT64 | Projected energy divided by total energy; the correlator-domain unknown-variance Gaussian GLRT. |
| Gaussian GLRT64 margin | Gaussian exact minus control, isolating normalization from removal of control subtraction. |
| Adaptive normalized matched filter | The Gaussian statistic in an independently estimated covariance metric, with fixed 0.25 shrinkage. |
| Two 32-symbol segments | Same 64 symbols, but independent complex amplitudes/phases in the two halves at a common CFO. |
| Lag-one differential | Normalized adjacent-symbol products, with phase-derived CFO quantized to the common grid. |

An adaptive control-margin diagnostic is also implemented. It is excluded from
the primary synthetic comparison because the exact and control projections can
have different noise covariances. Its recorded results are diagnostic only.

Gaussian/adaptive methods account for per-symbol template energy in both the
observation and steering vector. Current scores retain the raw correlations.
The Gaussian derivation concerns the correlation vectors; it does not recover
orthogonal raw-IQ energy discarded by the correlator. Adaptive covariance is a
plug-in estimate, not a full treatment of covariance-estimation uncertainty.

**55 tests pass; Ruff passes.** Tests include production-baseline equivalence,
independent least-squares likelihood oracles, complex covariance orientation,
identity-covariance equivalence, template-energy handling, pooled-frame batching,
shared exact/control noise, split isolation, corrupted input rejection, and
artifact-audit failure cases. The [independent verification receipt](verification.json)
recomputes 28 calibrated thresholds, 224 null/signal count summaries, and 196
joint detection/frequency summaries. It also compares 1,536 recorded candidate
scores across two acquisition regimes against the existing production scorer.
Maximum absolute score error is **2.22e-16**.

## Controlled detection results

The primary experiment uses **14 frames × 64 symbols**, a common unknown CFO
per trial, independent unknown frame phases, and the same 512-bin frequency
search. Timing is already acquired. The synthetic exact/control noise shares
the actual sampled Qin-template Gram matrix; the two projections are not
independent confirmations.

Each environment has 3,000 independent calibration nulls, 5,000 evaluation
nulls, and 600 signal trials at each of seven SNRs. Covariance training uses
512 separate frame rows per environment, plus a separate white-training control.
The final run took **38.7 seconds**. Source/configuration digests, seeds,
covariance training, scores and CFO arrays are preserved under
[synthetic/pooled14](synthetic/pooled14/).

Thresholds were frozen at a nominal **1% conditional false-alarm target** before
evaluation. The table reports threshold-exceedance probability, not yet correct
frequency acquisition:

| Detector | White, −15 dB | Colored AR, −12 dB | Tone, −12 dB | Phase instability, −12 dB |
|---|---:|---:|---:|---:|
| Current GLRT64 margin | 79.8% | 0.7% | 1.0% | 67.5% |
| Gaussian GLRT64 | 82.3% | 1.2% | 0.3% | 72.5% |
| Gaussian GLRT64 margin | 79.8% | 0.5% | 0.8% | 66.0% |
| Adaptive whitened filter | 77.8% | 85.5% | 100.0% | 64.2% |
| Two 32-symbol segments | 64.7% | 0.2% | 1.7% | 79.8% |
| Lag-one differential | 7.7% | 1.0% | 0.7% | 29.8% |

SNR is per normalized pilot correlation, not a measured receiver RF SNR. The AR
coefficient is 0.85; the coherent tone has 10 dB interference-to-noise ratio.
Phase instability is a within-frame random walk with 0.35 radian standard
deviation per symbol increment. These are explicit stress models, not fitted
descriptions of the recorded environment.

![Conditional detection curves](figures/detection.png)

Achieved false-alarm rates differ because calibration and evaluation samples
are independent. Here are the actual rates on 5,000 evaluation nulls:

| Detector | White | Colored AR | Tone | Phase-instability null |
|---|---:|---:|---:|---:|
| Current GLRT64 margin | 1.10% | 1.16% | 0.84% | 1.40% |
| Gaussian GLRT64 | 0.90% | 1.06% | 1.32% | 1.32% |
| Gaussian GLRT64 margin | 1.14% | 0.96% | 0.80% | 1.12% |
| Adaptive whitened filter | 1.16% | 1.10% | 0.78% | 0.88% |
| Two 32-symbol segments | 1.04% | 1.06% | 1.32% | 0.98% |
| Lag-one differential | 0.82% | 1.00% | 1.00% | 1.36% |

The phase-instability null is white noise with separate random seeds; only its
alternative contains phase instability. Full counts and 95% Wilson intervals
are in [summary.json](synthetic/pooled14/summary.json). These intervals condition
on the realized training/calibration; they do not include variation from retraining.
No evaluation outcomes were used to adjust the frozen operating thresholds.

A secondary [descriptive ROC calculation](descriptive_roc.json) compares the
methods at exactly 50/5,000 observed false alarms (1%). At the same displayed
SNRs, white-noise detection is 79.0% for current versus 82.8% for Gaussian;
phase-instability detection is 63.8% for current versus 70.8% for Gaussian and
80.2% for segmentation. This uses evaluation nulls to describe an ROC point;
it is not a newly qualified operating threshold.

Three implications are supported within these models:

1. **The white-noise improvement is modest.** The Gaussian-margin ablation
   closely tracks the current margin here. Removing control subtraction matters
   more than changing its normalization at this operating point. That does not
   justify removing specificity controls on real interference.
2. **Whitening depends strongly on representative training.** Replacing the
   matched covariance with independently learned white covariance lowers
   detection to 0.5% in the colored case and 0.3% in the tone case at −12 dB.
   Even this comparison recalibrates thresholds within each environment: it
   isolates covariance transfer, not transfer of an entirely frozen detector.
3. **Detection and useful frequency estimation differ.** Under phase instability
   at −12 dB, detection *and* CFO within 1 kHz occurs in 39.8% of trials for
   current, 42.0% for Gaussian, and 42.8% for segmentation. The much larger gain
   in threshold exceedance does not translate into an equally large CFO gain.

![Joint detection and frequency accuracy](figures/correct_frequency.png)

## Replay of existing recordings

The outcome-independent selection uses 24 DS5 visits: two per sample rate and
development/validation/holdout split, both receivers, and nonoverlapping 20 ms
windows starting at 0 and 40 ms. There are **96 receiver windows and 768 shared
candidate hypotheses** per acquisition regime. Input hashes are verified.
The real recordings have no detection or satellite-identity ground truth.

The primary [production-acquisition replay](recorded/production_final/results.json)
uses the existing full `acquire_symbolwise` numerical path with eight retained
candidates. Every method scores the identical candidate inventory and input
matrices. The [coarse-only replay](recorded/coarse_final/results.json) is a
separate diagnostic on the same recordings, not another independent dataset.

On the 32 holdout windows (16 nonoverlapping pairs):

| Detector | Same winning candidate as current | Timing/CFO-consistent pairs |
|---|---:|---:|
| Current GLRT64 margin | 32/32 | 3/16 |
| Gaussian GLRT64 | 24/32 | 3/16 |
| Gaussian GLRT64 margin | 31/32 | 3/16 |
| Adaptive whitened filter | 12/32 | 3/16 |
| Two 32-symbol segments | 17/32 | 3/16 |
| Lag-one differential | 13/32 | 4/16 |

Consistency means the top candidates differ by at most 5 kHz in reported CFO
and 4.4 microseconds in circular frame timing across windows separated by 40 ms.
It is a descriptive metric on all windows, without a truth-calibrated detection
gate. Bursts, multiple emitters, aliases, and low evidence can all change winners.
The one-pair differences do not establish improved tracking. All methods have
zero consistent pairs in development and three in validation.

For all 768 fixed candidate hypotheses, Gaussian and current CFO estimates are
**exactly equal**. Both maximize the same frequency-dependent numerator;
normalization/control changes affect ranking across candidates, not the
same-candidate peak location. Large changes between different winners include
alias and timing choices and must not be described as measured physical drift.

The production replay took **23.6 seconds wall time**: 21.88 CPU seconds for
shared acquisition, 0.85 for correlation extraction, and 0.37 for all seven
scoring variants together. These are combined Python/NumPy prototype costs,
not per-method speed rankings or ARM qualification.

Recorded adaptive covariance uses only **60 rows per rate for 64 dimensions**,
regularized with fixed 0.25 shrinkage. Training comes from separate development
visits at epoch/CFO zero and is transferred across receiver, epoch and candidate
CFO. Validation has the opposite edge to its per-rate training; holdout has the
same edge. Training observations are unlabeled and may contain pilots or
interference. This does not establish a correctly matched colored-noise model
for every candidate. See [recorded_notes.md](recorded_notes.md).

## Limits and disposition

- The synthetic experiment conditions on the correct acquired timing and
  maximizes one frequency bank. It does not estimate false alarms from the full
  data-selected timing/CFO search or a complete scan.
- Synthetic pilots have unit symbol energy, CFO is constant within each symbol,
  and the Gram geometry uses the 20 MS/s upper-edge template. Recorded rates are
  2.5--10 MS/s with actual template energies. Model success is not hardware recall.
- Synthetic trials use 14 frames; recorded candidates have 14--15 supported
  frames. Of the 96 production-current winners, 68 use 15 and 28 use 14.
- The primary replay preserves the current upstream proposal search. It cannot
  measure signals that a different acquisition strategy would recover outside
  that retained bank. Repeated experimentation on DS5 also limits external
  generalization despite session-disjoint splits within this experiment.
- No localization solver or measurement weights were changed. No position
  improvement is inferred from these detector statistics; a future localization
  comparison still requires matched fitted-c versus c=0 ablation.

The next useful step is a bounded covariance-transfer test on independently
selected saved recordings, including candidate-CFO conditioning and multiple
known negative/interference controls. Freeze that policy before comparing real
false alarms and known-signal recovery. Keep production unchanged pending that
evidence.

## Reproduction and artifacts

[PROTOCOL.md](PROTOCOL.md) records the design and
[synthetic_notes.md](synthetic_notes.md) gives detailed model assumptions.
The preliminary single-frame simulation is retained in
`synthetic/single_frame_aperture_ablation`; it is not the primary comparison.
An early recorded run correctly rejected outputs after a concurrent source
change; final regimes completed with stable source digests.

From the repository root:

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/pytest -q reports/2026_10_07_glrt_detector_comparison
.venv/bin/ruff check reports/2026_10_07_glrt_detector_comparison
env OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python reports/2026_10_07_glrt_detector_comparison/verify.py
env OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python reports/2026_10_07_glrt_detector_comparison/render.py
```

Fresh bounded executions, using new output directories:

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 180 .venv/bin/python reports/2026_10_07_glrt_detector_comparison/synthetic.py \
  --output /tmp/leo-glrt-synthetic-new
.venv/bin/python reports/2026_10_07_glrt_detector_comparison/recorded.py freeze \
  --acquisition production --output /tmp/leo-glrt-recorded-new
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  timeout 240 .venv/bin/python reports/2026_10_07_glrt_detector_comparison/recorded.py run \
  --acquisition production --output /tmp/leo-glrt-recorded-new
```

Figures are available as PNG and PDF under [figures](figures/). All raw RF was
already on disk; no radio collection, production deployment, or golden-fixture
change occurred.
