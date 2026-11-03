# N24 subkm agreement is not robust to chronological scan selection

**Changing only the 24-scan selection changes DS8 reference distance from 390 m to 1,877 m.** DS7 and DS9 remain below 1 km under the same chronological-rank rule used for DS10. Thus the earlier pooled N24 results do not establish that any time-spread set of 24 scans reliably reaches subkm agreement, and DS10's adverse result cannot be attributed solely to being a newer dataset.

| Dataset | Earlier block-selected N24 | Rank-selected N24 | Horizontal movement between fits | Shared scans / 24 |
|---|---:|---:|---:|---:|
| DS7 | 388 m | 454 m | 224 m | 7 |
| DS8 | 390 m | 1,877 m | 2,078 m | 8 |
| DS9 | 107 m | 341 m | 313 m | 6 |
| DS10 | Not tested | 1,092 m | — | — |

The first two numeric columns are spherical horizontal distances to the operator roof reference. The configured center alone is 809 m from that reference. The rank-selected fits beat the center only on DS7 and DS9. DS10's installation/reference continuity remains unverified. These are exploratory, overlapping, single-site comparisons rather than independent accuracy trials.

## Controlled change and remaining differences

The [protocol](PROTOCOL.md) preceded these fits. Apply `i*(N-1)//23`, i=0..23, to recordings sorted by start time and session ID in each full DS7/DS8/DS9 manifest. This exactly matches DS10's selection rule. The earlier N24 pool instead concatenated early, middle and late eight-scan blocks. The configuration, zero-height geometry, q020 likelihood, candidate-bank policy, optimizer/qualification and six-start rule remain unchanged.

Selection does not use signal quality, sample rate, satellite identity, fitted location or reference error. Every selected input already has a validated cache. DS9-F028 uses its previously validated recovery export; it is not replaced by another recording. There was no new input export, raw-IQ processing or RF acquisition.

Equal scan counts do not imply equal exposure, receiver quality, sample-rate composition, satellite geometry or orbit conditions. Changing recordings changes those observations together; this experiment demonstrates selection sensitivity without identifying its physical cause.

| Dataset | Earlier tracks | Rank-selected tracks | Earlier observations | Rank-selected observations |
|---|---:|---:|---:|---:|
| DS7 | 1,434 | 1,383 | 68,744 | 63,096 |
| DS8 | 1,434 | 1,419 | 64,384 | 63,460 |
| DS9 | 1,460 | 1,433 | 65,678 | 68,333 |

DS8's large displacement occurs with similar total observation counts. That does not rule out unequal information or systematic errors in particular recordings. Likelihood scores across different scan populations are not directly ranked as if they measured the same held target set.

## Verification

All 18 starts qualify, including all cold and timing-grid starts on each dataset. The highest qualified training score chooses each reported fit; no reference coordinate enters optimization or start selection. The three jobs complete in 135–141 seconds within their 180-second caps, without retries or omitted starts.

The input freeze verifies session/source-manifest identity, cached artifact hashes and exact configuration equality. The result auditor verifies all frozen source hashes, the exact six-start set, complete selected membership, qualified training-only selection and original reference-distance recomputation. The numerical likelihood/optimizer are reused unchanged from prior component-tested experiments; this study adds selection and execution bookkeeping, not a new estimator.

The [plan](plan.json) preserves selected ordinals, input artifacts, recovery status, overlap counts and hashes. `DS7/`, `DS8/`, and `DS9/` preserve each start and selected result. [summary.json](summary.json) includes distances, movement, counts and bindings to both comparison arms and the original DS10 baseline.

## Consequence for priorities

Retain the earlier successes as conditional results, but withdraw any inference that pooling 24 scans by itself solves the subkm objective. The matched selection rule yields subkm reference agreement on two of four datasets, with previously exposed data and unresolved physical/reference limitations. This descriptive fraction is not a calibrated deployment success rate.

Do not choose whichever subset lands closest to the reference. The next useful diagnostic is to compare the DS8 subsets on shared observations and examine what the newly included recordings contribute to the position/timing/association compromise. Any selection or weighting rule must be learned without target reference coordinates and tested on separate observations. The present result supplies a concrete within-dataset failure case for that work; it does not justify a tuned correction or establish the root cause.

No production change, new physical calibration or remote publication occurred. Reliable absolute subkm accuracy remains unverified.

## Reproduction

```sh
python3 reports/2026_09_29_rank24_control/prepare.py
OPENBLAS_NUM_THREADS=1 timeout --kill-after=10 180 uv run --no-project --with numpy --with scipy python reports/2026_09_29_rank24_control/run.py DS7
python3 reports/2026_09_29_rank24_control/summarize.py
```

Use a fresh output context, repeat the fit command for DS8 and DS9 before summarizing, and preserve the existing plan/results. Completed starts can be resumed only with the same verified plan hash; final results are created exclusively. `evidence.sha256` seals the current local protocol, source, plan, starts, outputs and report.
