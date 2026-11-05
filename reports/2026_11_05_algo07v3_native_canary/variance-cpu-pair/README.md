# Bounded variance batching: complete standalone comparison

2026-11-05. External development prototype; no deployment or runtime integration.

The candidate and integrated standalone baseline match **exactly** on DS26-0002:
both calibration arms, all science and audits, all eight PNG bytes, diagnostic
grid/path data and published result fields. Only the declared hierarchical
module differs. This is owned-engine equivalence, not full historical ALGO07
or dataset-wide qualification. [Comparison](comparison.json).

| Native GLRT ready through publication and supervisor exit | Observed seconds |
| --- | ---: |
| Integrated baseline | 244.383 |
| Bounded variance batching | 234.399 |

The candidate was **4.09% faster** in this pair. The baseline ran first; both used
CPUs 0–2, one BLAS thread, identical numerical budgets and a 1,200-second outer
limit. These shared-host timings do not establish a controlled population or
cumulative speedup. Resource observations are preserved alongside the receipts.
One pair does not establish performance qualification. Compare it with the
preceding pair and the alternating exact-call timings, retaining regressions.
Do not attribute changes in unchanged stages to variance batching.

| GNU time accounting | User CPU s | System CPU s | Max RSS KiB |
| --- | ---: | ---: | ---: |
| baseline | 265.14 | 6.06 | 2407056 |
| candidate | 251.78 | 7.36 | 2485072 |

CPU time includes waited-for children. It is separate from wall latency; host frequency and memory contention can still affect it.


![Complete path and stage observations](runtime.png)

The prototype groups independent equal-width variance products and reductions,
preserving each group's arithmetic and restoring group order before updating
precision. Batches above 1 MiB per stacked matrix tensor and singleton groups
use the original reductions. No observations, priors or iterations are removed.

The preceding native probe compared all 6,772 calls exactly and measured an
11.17% kernel reduction. Nine additional tests now cover the exact batch-memory
boundary, strided arrays, unequal feature scales, noncontiguous group labels,
mixed singleton/empty groups and short iteration budgets. All pass.
[Boundary tests](boundary-tests.xml), [preceding evidence](../README.md).

| Stage | Baseline seconds | Candidate seconds |
| --- | ---: | ---: |
| native_preparation | 8.453 | 8.214 |
| recovery_catalogue | 5.452 | 5.316 |
| initial | 24.400 | 23.140 |
| conservative | 19.672 | 18.124 |
| family | 17.604 | 16.830 |
| signed | 2.547 | 2.441 |
| cavity | 7.521 | 7.530 |
| inventory | 0.204 | 0.194 |
| predictive | 75.990 | 68.723 |
| numerical | 15.534 | 14.770 |
| gap | 0.002 | 0.001 |
| residual | 0.195 | 0.186 |
| residual_screen | 18.186 | 18.216 |
| addition | 0.002 | 0.002 |
| incumbent | 0.268 | 0.259 |
| ranking | 6.904 | 6.742 |
| admission | 10.643 | 12.675 |
| final | 0.061 | 0.065 |
| plot_evidence | 15.653 | 14.931 |
| png_rendering | 5.521 | 5.578 |

Next: resolve the complete-path timing regression and extend this candidate
through the larger native guarded-reassociation case before integration.
Full DS26 retains 159 fast members, 158 available
inputs and one unavailable member. Ordinary admission, full historical
metadata qualification and the cumulative tenfold target remain open.

Reproduce with [pair runner](../run_variance_cpu_pair.py) and
[renderer](../render_variance_pair.py); immutable inputs and sources are recorded
in [plan](plan.json). Raw evidence: `/srv/bulk/leo-dev/algo07v3-variance-cpu-pair-20261105`.
