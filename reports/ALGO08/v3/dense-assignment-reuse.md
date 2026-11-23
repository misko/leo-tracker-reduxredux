# Exact reuse across competing dense cold assignments

The three leading DS30-0008 assignments shared **86.2–91.5%** of rows in complete noise-normalized track blocks at the common trial position. Every final noise weight and common posterior coefficient differed in every cross-assignment comparison. The reusable blocks feed the unweighted per-track Gram and right-hand side. Each assignment still needs its own joint robust posterior. The entire cold stage costs **5.724 CPU s** in the 26.105 s combined solver, so even a free cold stage leaves **20.381 s** against the 16 s target. [Saved census](measurements/dense-assignment-reuse.json) · [Full solver accounting](regional-dense-pair.md)

## Common-site operands

The seven unique ranked assignments use the same 112 tracks and 4,896 curved rows at the offered-region centre, with zero orbital phase reference and the original fixed-zero calibration used for discovery. The comparisons retain the track order and identify orbital and phase nuisance columns by causal catalogue identity, even when their global matrix slots move. All pairs shared every original noise scale, and the top three also shared every alias-adjusted observed value. The orbital response can change when the owner changes. A reassignment can also change physical orbit support on a track whose own satellite and alias stay fixed. [Observer and operand checks](dense_assignment_reuse.py)

| Ranked assignments | Same satellite and alias, tracks | Same normalized design and response, tracks / rows | Same fixed priors, common coefficients | Same final noise weights / radio coefficients |
|---|---:|---:|---:|---:|
| 1 and 2 | 101 of 112 | 100 / 4,326 | 255 of 255 | 0 of 112 / 0 of 30 |
| 1 and 3 | 100 of 112 | 99 / 4,219 | 259 of 259 | 0 of 112 / 0 of 30 |
| 2 and 3 | 105 of 112 | 105 / 4,479 | 265 of 265 | 0 of 112 / 0 of 30 |

Across all 21 assignment pairs, complete reusable blocks covered 3,120–4,584 rows and all common fixed prior precisions matched. Initial robust weights follow the same unit initialization. Each next weight depends on conditional residuals and shared posterior covariance, which change with ownership. All common final nuisance coefficients, including the shared hardware and smooth receiver coefficients, changed across the 21 pairs. This supports per-track pre-weight statistic reuse at the same site and phase reference. Reusing weighted normal factors or completed posteriors would change the measured likelihood. The earlier Schur work exposes how the shared receiver block couples the groups. Its separate exact audit found full-rank changes between adjacent robust factors. [Schur decomposition](../single-core-2x/solver-schur.md) · [Exact Schur reuse audit](../single-core-2x/solver-anderson.md#exact-schur-reuse-audit)

## In-scope calls and budget

The complete cold route used **67 native likelihood calls** and **3,353 robust updates**. The prior ranking optimizations were active. Final-ranking scores and the winning race matched the earlier saved packet. The three finalists visited 29, 5 and 5 distinct sites respectively. Each pair shared just three zero-phase trial sites. In addition, the centre call repeated exactly once from initial ranking to the race for each of the three finalists, within its own assignment. The complete adapter clock for all seven centre evaluations together was 0.170 CPU s, a generous ceiling for caching those three exact repeats. [Same-packet cold-rank control](measurements/cold-track-row-reuse.json.gz) · [Measured call scopes](measurements/dense-assignment-reuse.json)

| Stage | Native likelihood calls | Robust updates | Native adapter CPU |
|---|---:|---:|---:|
| Discovery passes before exact rank | 16 | 690 | 0.375 s |
| Exact centre rank | 7 | 326 | 0.170 s |
| Three prefixes and winner completion | 44 | 2,337 | 1.105 s |
| Total | 67 | 3,353 | 1.650 s |

The entire adapter includes validation, copying, factorization, robust updates and final readout. Making all of it free would cover just **16.3%** of the required 10.105 s saving. Reuse of pre-weight track contractions alone can cover only part of that adapter. The later fine salvage evaluated 2,580 single-track profiles after screening 49,024 support trials. It chose at most one alternative per track and formed one post-salvage assignment. The post-salvage check, predictive nomination and final two calibration arms follow that assignment rather than reranking all alternatives with the joint likelihood. Even granting **all** cold work, salvage and post-salvage predictive work for free leaves **17.353 CPU s**. The fixed-owner warm fit and predictive-grid work already have separate measured costs. [Lighter joint estimator](lighter-joint-estimator.md) · [Predictive grid](grid-predictive-reduction.md) · [Cross-arm posterior limits](grid-cross-arm-posterior.md)

The study stopped at one observer-only cold replay because the stage ceiling already misses the target. It used the original signed short detector packet, installed graph, causal TLE archive, native geographic precheck, centre-row reuse and original finalist race. It reproduced the saved branch, prefix scores and winning endpoint exactly. The numerical route stopped after discovery. The complete dense control supplies the published paired calibration evidence. Twenty-nine focused tests passed. [Complete dense control](measurements/regional-dense-pair.json) · [Component tests](../../../tests/pipeline_eval/test_dense_assignment_reuse.py)

To reproduce, run `dense_assignment_reuse.py NEW_RECEIPT` with the Gauss release Python, installed payload first on `PYTHONPATH`, and `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `BLIS_NUM_THREADS` and `NUMEXPR_NUM_THREADS` set to 1. Use the shared Gauss lock, CPU 2, nice 15 and best-effort I/O priority 7. Use the original pinned local saved publication and native libraries named in the runner. [Runner](dense_assignment_reuse.py)
