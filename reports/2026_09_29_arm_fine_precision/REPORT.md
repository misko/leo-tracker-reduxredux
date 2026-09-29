# FP32 fine FFTs help ARM; the tested FFT batches do not

FP32 fine-frequency FFTs reduce restricted-search CPU by **11.0%**, from
5.461 to 4.860 seconds per 120 ms dual-RX dwell on PLUTO+ CPU0. Guarded FP32
costs 4.950 seconds, a **9.4% reduction**. Both preserve all positive/negative
decisions of the previous restricted search on the existing 704-dwell DS7
subset and recover **19,400/19,581 standard-pipeline hits (99.08%)**. At
2.5 MS/s the corresponding count is **4,551/4,573 (99.52%)**.

This is an incremental improvement, not real time or exact standard output
equivalence. The inherited restricted method still returns 18,328 unmatched
positive entries and misses 181 original hits. Precision changes did not fix
these properties. Production analysis is unchanged.

## What was tested

Two SOL agents independently implemented the precision and batching variants.
The root coordinator reviewed code, ran standard-hit audits and serialized
physical-ARM tests. All variants retain the existing timing proposals, lazy
epoch cache, candidate count, frame count and final FP64 GLRT scorer.

FP32 changes fine-FFT input, transform, cached complex spectra and per-bin
magnitude to float. Sample/template products, energy/normalization, accumulated
scores, ranking arithmetic and downstream scoring remain double. ARM FFTW's
float library was built with NEON enabled. This is targeted mixed precision,
not global fast-math or FP32 throughout the detector.

Guarded mode recomputes the complete requested fine-frequency range using
original FP64 arithmetic when scores are nonfinite, the top two scores are
within `256*FLT_EPSILON*max(1,abs(best_score))`, or the interpolation parabola
is shallow/near its clamp. Constants were fixed before cohort runs. This is an
engineering safeguard, not a proven error bound or guaranteed equivalence.

The independent batching prototype uses FP64 FFTW `plan_many` for groups of
four or sixteen frames of an epoch, without changing scoring accumulation
order. It does not use extra CPU cores or batch complete dwells. See the
[batch implementation](../2026_09_29_arm_fine_batch/README.md).

## Measured ARM performance

Same four saved 2.5 MS/s dual-RX dwells on .15 CPU0, 88 windows and 704
candidate entries. No RF, concurrent capture or concurrent analysis jobs.
Raw and guarded v2 timings each average two runs of these same four dwells;
baseline and batch variants have one current run. Repeats are not new data.
Plan allocation/setup and teardown are included in total search CPU. File I/O,
initial workspace creation and proposal construction are outside search timing.

| Fine FFT variant | Fine stage CPU s/dwell | Total search CPU s/dwell | Search CPU change | Standard hits recovered on ARM |
|---|---:|---:|---:|---:|
| Existing FP64 lazy cache | 2.841 | 5.461 | Reference | 119/119 |
| Raw FP32 | 2.267 | **4.860** | **11.0% less** | 119/119 |
| Guarded FP32 | 2.355 | **4.950** | **9.4% less** | 119/119 |
| FP64 batches of 4 | 3.225 | 5.854 | 7.2% more | 119/119 |
| FP64 batches of 16 | 3.409 | 6.061 | 11.0% more | 119/119 |

All ARM variants return 258 positive entries, of which 139 are unmatched to
the 119 standard positives. Both batch variants preserve all 704 candidate
objects exactly. Precision changes numerical values, so their quality claim
comes from the standard-hit audit rather than object equality.

The raw repeats cost 4.856 and 4.863 seconds/dwell; guarded repeats cost 4.954
and 4.947. The fresh FP64 reference agrees closely with the earlier 5.461-second
measurement. `arm-aggregate.json` contains precise stages and source hashes.

Adding the **separately measured** 851.639 ms FP32 proposal cost yields:

| Method | Search + proposal stage sum | Relative to previous stage sum |
|---|---:|---:|
| FP64 fine FFT reference | 6.313 s/dwell | Reference |
| Raw FP32 fine FFT | **5.711 s/dwell** | 9.53% less CPU, 1.105x speedup |
| Guarded FP32 fine FFT | **5.802 s/dwell** | 8.09% less CPU, 1.088x speedup |

These are not fused capture measurements. Even the raw variant remains 47.6
times the 120 ms real-time allowance and 79.3 times the 72 ms budget for 40%
headroom. The separate direct-CI16 final-scorer optimization is not integrated.

## Recovery against standard analysis

The initial 32-dwell panel uses fixed FP64 timing proposals to isolate the FFT
change. All four variants recover 838/843 standard hits and return 884
unmatched positives. Both batch sizes preserve all 5,632 candidate objects.
Because batches are slower on ARM, they were not expanded to 704 dwells.

The two promising FP32 modes were then run on all **704 development dwells
from 88 DS7 recordings**, using the already qualified FP32 timing proposals.
This is 15,488 windows and 123,904 candidate entries, not full DS7 or an
independent holdout. Actual downstream GLRT was rerun; baseline coordinates
were never supplied to discovery.

| Rate | Windows run | Standard hits | Previous restricted recovery | Raw FP32 recovery | Guarded FP32 recovery |
|---|---:|---:|---:|---:|---:|
| 2.5 MS/s | 3,344 | 4,573 | 4,551 | 4,551 | 4,551 |
| 5 MS/s | 4,752 | 5,466 | 5,420 | 5,420 | 5,420 |
| 7.5 MS/s | 4,048 | 5,186 | 5,137 | 5,137 | 5,137 |
| 10 MS/s | 3,344 | 4,356 | 4,292 | 4,292 | 4,292 |
| **Total** | **15,488** | **19,581** | **19,400** | **19,400** | **19,400** |

Matching is one-to-one within the same receiver/window, margin >=0.025,
<=2 samples and <=8 kHz. Both precision modes change **zero candidate positive
decisions and zero per-window recovered-hit counts** relative to the prior
restricted method. Maximum paired margin change is 1.178e-8; maximum acquired
and tracking CFO change is 0.003195 Hz. These are observed bounds, not future
guarantees. Both still produce exactly 18,328 unmatched positives.

Guarded mode falls back on 2,860/123,904 candidate searches (2.31%), all for
near ties; on ARM it falls back on 15/704 (2.13%). No measured recovery benefit
over raw FP32 appeared on this cohort. Guarded mode is the conservative research
option; raw mode documents the lower cost. Neither is automatically promoted
to production based on this development set.

## Where the remaining fine-stage time goes

A separate v3 diagnostic adds timers without changing the algorithm and
reproduces every candidate object of ARM raw-v2. Per-dwell attribution is:

| FP32 fine-stage work | CPU ms/dwell |
|---|---:|
| FFT execution | 1,675.841 |
| Input/template preparation | 318.626 |
| Spectrum allocation/copy | 168.230 |
| Magnitude and score accumulation | 140.323 |
| Plan setup | 11.517 |
| Cache teardown | 24.939 |

These are diagnostic substage totals, not additive to the search table.
Frequent timer calls introduce overhead; v2 remains the performance reference.
The diagnostic suggests that eliminating or shortening transforms has more
remaining potential than optimizing plan setup alone. It does not establish
why every FFTW batch is slower; batching larger buffers can change cache and
allocation costs. Only these two batch layouts were tested.

Next useful experiments are exact reuse of supported contributions between
overlapping windows, and fresh timing acquisition with narrower candidate
frequency ranges. Any reduced transform must retain required bins and be
audited for changed candidate ranking, interpolation and final detections.

## Validation and artifacts

Host all-rate full/partial-window C tests and sanitizer checks pass for FP32
and batching; evaluator contract tests pass. Physical-ARM component receipts
are in `arm-units.json`. Cohort folders contain complete manifests, exact
standard-hit audits and comparisons. `aggregate.py` rebuilds performance and
diagnostic summaries from completed hash-bound runs.

Selected performance builds are precision raw/guarded **v2**. Initial v1
results are retained but superseded because allocation-failure cleanup was
fixed; normal-path arithmetic did not change. Top-level source/build.py now
describe diagnostic v3. Publication archives v2 and diagnostic source snapshots
with their original compile receipts so the timed versions remain reproducible.
Batch build receipts are immutable; additional complete source provenance is
in separate `complete-provenance.json` files. Raw candidate rows, IQ and binaries
stay local with their hashes recorded; code, reports and summaries are published.
