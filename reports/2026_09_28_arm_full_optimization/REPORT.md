# ARM full-inventory optimization, 2026-09-28

This experiment keeps the original search inventory: 11 overlapping 20 ms
windows per receiver, two receivers, all coarse timing/CFO hypotheses, all
supporting frames, and eight retained acquisition candidates per window.
Final GLRT remains FP64 at each original integer epoch. No live radio collection
is performed, and production analyzer code and published contracts are unchanged.

## Matched-input 2.5 MS/s ARM timing

The same four probe-zero receiver windows are used in every row below, each with
three timed repetitions on PLUTO+ `192.168.1.15`, CPU0. Inputs are in RAM before
the timed kernel. Setup, file transfer, diagnostic grid evaluation and JSON
output are outside the kernel timing. These are isolated analysis measurements,
not simultaneous-capture or end-to-end deadline measurements.

| Method | Mean CPU time / receiver window | Relative to first full-search port |
|---|---:|---:|
| FP64, insertion sort (previous report) | 5,291.81 ms | 1.00× |
| FP64, merge sort (previous report) | 4,459.50 ms | 1.19× |
| FP32/NEON coarse, FP64 refinement (previous report) | 3,337.59 ms | 1.59× |
| FP32/NEON coarse + guarded conditioned screen | 2,740.62 ms | 1.93× |
| Same, with pruned FP64 fine FFT | 2,745.45 ms | 1.93× |

The conditioned screen provides a further 1.22× improvement over the previous
coarse-FP32 method. Pruned FFT is neutral/slightly slower at 2.5 MS/s on this
ARM fixture, so the unpruned version remains the primary 2.5 MS/s candidate.
All five methods preserve the two original positive hits in this four-window
fixture; larger recovery evidence is reported separately below.

The primary candidate's mean stage times are about 1,213 ms coarse search,
904 ms fine FFT, 495 ms conditioned search, 76 ms verification and 38 ms final
GLRT. Coarse search and acquisition still dominate the work.

## What the conditioned screen changes

Every conditioned frequency is evaluated with an FP32 complex dot product,
split into 64-sample blocks. Each block has at most 16 products per vector lane;
block results accumulate in FP64. Template construction, signal energies and
normalization remain FP64.

Bins within twice a `128 * FLT_EPSILON` normalized-score guard of the screened
maximum are recomputed in FP64. The winning recomputed score and CFO feed the
original verification and final GLRT. This is an engineering error guard backed
by numerical and corpus checks, not a proof of universal equivalence for every
possible input. The research switch is optional; default builds retain FP64
conditioned evaluation.

This method does not omit a GLRT window or remove a retained candidate. On the
64-dwell development cohort, it screens 461,064 conditioned bins and recomputes
12,988 of them in FP64. The original coarse-FP32 approximation remains enabled;
its coarse scores do not satisfy strict FP64-grid tolerance. Recovery and final
candidate parity are therefore measured separately from coarse-grid parity.

## Development-cohort quality

`COHORT_SUMMARY.md/json` and `results/{baseline64,screen64,pruned_screen64}/`
contain a metadata-selected 64-dwell host check spanning eight recordings,
all four rates, and both edges. Each method executes all 1,408 windows and
11,264 candidate evaluations. Both optimized variants recover all 1,669
original positive candidate hits and all 691 original positive windows, with
zero ordered epoch/acquired-CFO/tracking-CFO/exact/control/margin audit errors.
This is host numerical evidence, not an ARM speed measurement.

## Larger mixed-rate DS7 recovery test

The primary unpruned-screen method then completed all **704 sealed dwells**
spanning all **88 recordings** in the existing large subset. It executed all
15,488 scheduled 20 ms receiver windows and 123,904 candidate evaluations.
SOL's independent audit derives the denominator from every selected original
baseline window and uses maximum one-to-one hit matching.

| Rate (MS/s) | Dwells | 20 ms windows executed | Original positive windows / recovered | Original positive candidate hits / recovered |
|---|---:|---:|---:|---:|
| 2.5 | 152 | 3,344 | 1,682 / 1,682 | 4,573 / 4,573 |
| 5 | 216 | 4,752 | 1,874 / 1,874 | 5,466 / 5,466 |
| 7.5 | 184 | 4,048 | 1,933 / 1,933 | 5,186 / 5,186 |
| 10 | 152 | 3,344 | 1,518 / 1,518 | 4,356 / 4,356 |
| Total | 704 | 15,488 | 7,007 / 7,007 | 19,581 / 19,581 |

There are no missing windows, lost positive hits or added positive hits. This
is **100% positive-hit recovery on this subset**, not exact equality of every
intermediate result. One negative candidate in one 7.5 MS/s window selects a
different coarse CFO region and changes four ordered candidate positions.
The remaining 15,487 windows pass all checked ordered final-candidate fields.

Terra isolated that difference using a coarse-FP32-only reproduction: it occurs
before conditioned screening. `DIVERGENCE_AUDIT.md/json` records the original,
FP64-native and coarse-FP32 cases. Both versions of the changed candidate remain
below the positive threshold, and every positive hit in its dwell is recovered.

`FULL_COHORT_SUMMARY.md/json`, `independent_summary.py` and
`results/screen704/` preserve the independent audit and compressed raw evidence.
This larger test runs the native C method on the host. It covers about 0.36% of
DS7's 194,934 dwells, not full DS7, and does not substitute for ARM timing or
an ARM run of all 704 dwells.

## Whole-dwell ARM check

`arm-cohort-02/` contains four metadata-selected 2.5 MS/s dwells, covering the
first and last lower/upper entries in the input inventory (ordinals 184, 703,
48 and 679). The runner loads each saved dual-receiver CI16 dwell into RAM,
then executes all 11 windows on both receivers with a reused workspace on CPU0.
There are 88 executed windows and 704 candidate evaluations, with zero ordered
comparison errors against the sealed original.

The method recovers **119/119 original positive candidate hits** and **49/49
original positive windows**. Mean kernel CPU time is **60.314 seconds per dwell**
or **2.742 seconds per receiver/window**. This is a measured full-dwell sum,
not an extrapolation from probe zero. ARM block-dot tests also pass. Source,
binary, NPY and transferred-CI16 hashes are retained with the raw results.

This phase has no simultaneous capture load. Its runtime is already far above
the real-time budget, so it cannot demonstrate the requested headroom. The
incomplete `arm-cohort-01/` receipt records an unavailable SFTP transport before
any binary ran; the completed run uses verified SCP transfers.

## Reproduction and validation

`build.py` snapshots native sources and creates source/binary/compiler receipts.
The primary variant uses `--coarse32 --conditioned-screen`; `--pruned` adds
the optional fine-FFT experiment. `--arm` builds static Cortex-A9/NEON binaries;
`--sanitize` enables host AddressSanitizer and UndefinedBehaviorSanitizer.

`cohort.py` evaluates saved dual-receiver CI16 dwells against the sealed original
Python results. The default selects 64 dwells; `--all-sealed` selects all 704
available sealed inputs. Every receiver/window record has a fixed inventory;
missing, duplicate and unexpected records fail the audit. Positive matching is
one-to-one, with a two-sample timing and 8 kHz tracking-CFO tolerance; ordered
parity additionally requires exact epochs and much tighter numerical tolerances.

`test_screen.c` exercises block boundaries, cancellation and dynamic range;
`test_fft_pruned.c` covers all four FFT sizes, wrapped ranges, sparse inputs and
aliasing. The 16-probe sanitizer run completed with no diagnostics and preserved
22/22 positive hits. Its strict coarse-grid comparator failures are expected for
FP32 coarse arithmetic and are retained in the raw evidence.

The prior full-search report's 46-file hash manifest remains unchanged. No
quality claim here extends to the entire DS7 dataset, and the 40% simultaneous
capture headroom goal remains unverified. The current full-inventory analysis
is still far from real time.
