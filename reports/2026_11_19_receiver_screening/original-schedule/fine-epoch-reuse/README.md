# Exact reuse across original capture refinement ranks

The exact guarded cache cut complete detector CPU by **21.2%** on eight genuine conditioned recheck visits. Across the 20 outcome-blind timed visits, its mean CPU was **1.1% lower** and its paired median was **0.5 ms slower**. Sharing the weighted aperture at a repeated epoch increased mean CPU by **0.4%**. All **380 timed calls** reproduced the exact canonical public and projected detector output and the same sequence of conditioned decisions. [Stage figure](stage.pdf) · [Timing and hit-rate summary](summary.json)

The original detector ran 80 primary evaluations, eight 22-anchor retries and one direct conditioned recheck on 40 new signed dual-IQ visits. The trace covered **712 fine grids**. Seventy-six revisited a physical integer epoch within an evaluation, and only eight repeated the full fine input grid exactly. All eight came from the same conditioned recheck. Exact grid keys include the receiver, epoch and frame starts, pilot template, symbols and signed binary64 CFO values. [Visit and source lock](input-lock.json) · [Per-visit census](profile-counts.json)

## What repeats and what the variants share

The previous four-frame implementation vectorized the FFT across frames of one candidate. This study retains that implementation. The different-origin case can share the unrotated weighted aperture and denominator at a repeated epoch. It still applies each historical CFO rotation and calls the same four-frame FFT. Component checks with overlapping signed CFO grids observed distinct values at shared physical frequencies when the grid origin was changed. Shifted-bin reuse would therefore change the existing statistic at binary64 precision. [Earlier frame batching](../../retry-and-transfer/fine-batch/README.md) · [Cache source](../../../../tools/pipeline_eval/variants/fine_epoch_reuse.py) · [Signed CFO and scope tests](../../../../tests/pipeline_eval/test_fine_epoch_reuse.py)

The guarded candidate stores the existing coarse grid, complete fine-score tuples and normalized held scores within one physical evaluation. It only serves an identical key when the existing conditioned bank has already requested a direct recheck. Cached results require the same IQ array, byte-equal template, and the same relevant physical and transform settings. The conditioned scores still run through the direct route, and the acquisition ranking and subsequent GLRT remain the producer's own. A new evaluation clears those entries before a second receiver or an original peer retry uses them. [Exact guard and waveform comparison](qualification-lock.json)

Two complete coarse ledgers estimate how often that narrow fast path is accessible. DS26-0237 had **205 rechecked visits of 6,766 (3.03%)**, with 185 primary and 21 retry rechecks. DS29-0082 had **129 of 4,868 (2.65%)**, with 121 primary and eight retry rechecks. The ledger identifies anchor counts from the fixed inverse-FFT work and counts numerical rechecks separately from logical receiver evaluations. The eight timing witnesses deliberately select rechecks and have their own denominator. [Lower-edge coarse ledger](../../receiver-deadline/selector-waveform/cache.csv) · [Upper-edge coarse ledger](../../pilot-search-and-region/field-exact-waveform/coarse.csv)

| Port on the 40 held profiles | Calls | Same physical epoch and aperture | Repeated exact key | Exact repeats during the initial pass / recheck |
| --- | ---: | ---: | ---: | ---: |
| Fine search | 712 | 76 | 8 | 0 / 8 |
| Conditioned search | 712 | 76 | 26 | 18 / 8 |
| Held single-frequency score | 2,136 | 228 | 78 | 54 / 24 |

At repeated fine epochs, 13,355 requested CFO cells overlapped out of 220,072 total. Five fine requests used 15 frames and 707 used 14. The held trace found zero additional exact fine-grid matches across the primary and 22-anchor evaluations of the same physical receiver. On the eight recheck witnesses, four repeated primary evaluation and four repeated a 22-anchor retry. Their instrumented duplicate work averaged 164 ms for the coarse grid, 36 ms for fine grids, and 24 ms for held scores. The recheck still paid about 90 ms of direct conditioned scoring on the profiled host. [Profile rows and waveform hashes](qualification-lock.json)

## Complete detector clocks and retained state

Apply a second fixed hash to the 40 held visit IDs to select five per recording for timing. Run five interleaved repeats on CPU 12 after one warm call in each arm. The timed boundary begins at resident dual CI16 and ends after the detector and native projection. The eight independent recheck witnesses use the same paired timing and the original and guarded arms. [Frozen timing roster](timing-lock.json) · [Individual clocks](stage.csv)

| Cohort | Mode | Mean complete CPU (ms) | Paired median change (ms) | Mean change (%) |
| --- | --- | ---: | ---: | ---: |
| 20 held visits | Original prepared detector | 510.9 | 0.0 | 0.0% |
| 20 held visits | Same-epoch aperture | 512.9 | −5.9 | +0.4% |
| 20 held visits | Guarded recheck reuse | 505.2 | +0.5 | −1.1% |
| Eight guard witnesses | Original prepared detector | 964.0 | 0.0 | 0.0% |
| Eight guard witnesses | Guarded recheck reuse | 759.2 | −208.8 | −21.2% |

The 100 held calls in the aperture arm hit the two-entry cache 110 times across 1,800 fine transforms. It retained at most **3,062,632 bytes** of weighted samples and denominators while keeping the existing 2,957,040-byte four-frame workspace. The guarded candidate retained up to **2,324,936 bytes** of coarse arrays and estimated score objects within one evaluation. Its constructor took 15–19 µs CPU. The original batch and aperture instances both ran the existing startup arithmetic check. Construction consumed 40–230 ms and 31–112 ms CPU, respectively, in first-then-second order in the same workers. Mixed-mode RSS high water was 191–223 MiB. [Initialization and memory](summary.json)

Every timed recheck hit one coarse grid, eight fine-score tuples, and 24 held scores. The held benchmark contained one such visit, observed five times. The guarded arm retained the complete original sequence of direct conditioned scoring, including the 320 calls on diagnostic rechecks. The timing evidence supports a targeted reduction of recheck cost. The ordinary panel shows small mean differences with mixed paired results. [Complete outcome seal](qualification-lock.json)

## Reproduce

Use a new scratch directory on the replay host. Run `freeze` and `run` in the profiling module for the four signed recordings. Run `freeze` and `run` in the benchmark module against those same profile receipts. The results module accepts the work directory and publishes the timing rows and stage figure. The benchmark reused the qualified AVX2 fine-frame library. [Profile command](../../../../tools/pipeline_eval/qualification/fine_epoch_trial.py) · [Timing command](../../../../tools/pipeline_eval/qualification/fine_epoch_benchmark.py) · [Results command](../../../../tools/pipeline_eval/qualification/fine_epoch_results.py)
