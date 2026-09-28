# DS7 sparse and progressive GLRT search

At 2.5 MS/s, progressive search reduces mean CPU per dwell from **1,243.5 ms to 441.0 ms (2.82×)** while recovering all **32/32** original receiver/visit confirmations. Four windows with two candidates reduce CPU to **295.3 ms (4.21×)** while recovering **29/32 confirmations (90.6%)**. Their positive-hypothesis recovery is only 36.1% and 22.9%, respectively: these are detection-oriented gains, not full scientific-output equivalence.

This experiment implements and times the reduced-window and candidate-count designs from the previous retrospective screen. It also implements a progressive four-window search that expands each unconfirmed receiver independently, reusing previously computed probes. This is an experimental detector harness; production analysis and persisted contracts are unchanged.

SOL owns the search implementation and method tests. Terra owns the independent evaluator, completeness tests, and scientific audit. The root runner owns saved-IQ replay and source/input receipts.

## Scope

Same frozen 28 saved dual-RX 120 ms DS7 visits as the preceding experiment: 16 at 2.5 MS/s, four each at 5, 7.5 and 10 MS/s. All searches execute on CPU0 of an Intel Core Ultra 9 285K server with numerical threads fixed to one. Two repeats use fresh method instances and rotated method order. Timing includes CI16 conversion and all detector work, including progressive expansion. File reads, decompression, output serialization, waterfall generation, downstream Doppler processing and publication are excluded. No radio is used.

The original and exact-optimized baselines are rerun in the same experiment. The original uses the preceding benchmark's SHA-pinned historical acquisition/scoring modules. Scientific results use repeat zero only; the second repeat checks reproducibility and contributes timing. CPU and wall times are mean per-visit medians across both repeats.

This is a shared host and the replay runs at niceness 19. CPU time is the primary compute-cost comparison; elapsed time also includes scheduling delays. All delays remain in the rows and summary. For example, the second-repeat six-window 2.5 MS/s visit 1121 took 0.643 s CPU but 1.998 s elapsed, and a six-candidate 7.5 MS/s call took 6.447 s CPU versus 9.050 s elapsed. These were not removed as outliers or rerun selectively. Two repeats do not establish production latency tails.

The cohort was already examined when choosing these designs. Results are development measurements, not an independent validation or a population-wide promise of 90% or 80% recovery. In particular, each higher-rate stratum contains only four visits. All selected visits use upper-edge targets (indices 4–7); lower-edge recovery was not measured. The experiment retains missing detections and slow cases instead of filtering them out.

## Recovery contract

The primary 90%/80% target concerns original confirmed **receiver/visit pairs**, requiring two fresh positive probes separated by at least 20 ms and agreeing within 8 kHz. Identity-matched recovery uses the frozen scorer, including one-to-one matching within 2 us and 8 kHz at the same receiver/probe. Positive-hypothesis and positive-probe recovery are separately reported. A method that preserves a confirmation may still remove most original evidence and change which hit was first.

Sparse outputs contain only executed probes, with their real indices and timestamps. Skipped probes are not synthesized as negative observations. Decisions are folded chronologically even when progressive execution visits indices out of order. Full-output equality is intentionally stronger than the detection-recovery target.

The progressive initial schedule is 0,3,6,9 (start times 0,30,60,90 ms), with eight candidates. It then visits the remaining indices in increasing order only for receivers lacking a fresh confirmation. Already processed probes are never repeated. Once a receiver confirms, its expansion stops; the other receiver continues independently. Receivers without a hit eventually consume a complete search.

This is batch processing of an already captured dwell, not a streaming scheduler: an added early probe may confirm against a later initial probe whose samples are already available. Timing includes each repeated inexpensive chronological fold. The experimental fixed schedules admit the frozen 120 ms/11-probe geometry; other dwell durations need an explicitly designed schedule and tests. Candidate budgets change the actual acquisition request, so measured outputs, not a slice of original candidates, determine recovery.

The preliminary retrospective candidate-limit screen is not the implementation: acquisition first retains coarse peaks, refines them, and then reorders the survivors by verification evidence. Asking for two coarse candidates can therefore return a different subset from slicing the first two entries of the final eight-candidate ranking. Actual executed candidate-limited recovery is the authoritative measurement here.

### Why progressive search preserves confirmation existence

Under deterministic, independent per-probe scoring with the same eight-candidate configuration as the complete detector, the confirmation rule is an existence predicate that cannot lose a valid pair when more observations are added. Each receiver either confirms on a subset (that pair is also present in the full search) or exhausts all eleven probes (and therefore sees every full-search pair). Thus the per-receiver existence decision is preserved under these assumptions. This does not preserve first-hit selection, margins, candidate history, or positive-hypothesis coverage. A deterministic 96-scenario test checks this property against an independent pair oracle, including CFO boundary cases, absent signals, independent receivers, exhaustive negative searches, and absence of duplicate work.

## How to use the results

See [the measured tables](RESULTS.md) for the priority 2.5 MS/s comparison, all four rates, per-rate 90%/80% choices, and mixed-rate averages. Threshold-based winners are selected on this development cohort and need a new validation cohort before deployment.

Across the actual mixed-rate cohort, four windows with two candidates use **1,198.8 ms CPU versus 3,837.4 ms original (3.20×)** and retain **39/42 confirmations (92.9%)**. Three windows with eight candidates use **1,008.3 ms (3.81×)** and retain **36/42 (85.7%)**. Progressive search retains **42/42**, but its mixed-rate speedup is **1.51×**, reflecting the expensive exhaustive searches on unconfirmed receivers. A lower recovery target does not always buy additional speed: at 2.5 MS/s, four windows/two candidates are already faster and recover more confirmations than three windows/eight candidates.

If the target instead means recovering 90% or 80% of individual positive hypotheses, the all-window six- and four-candidate variants are the relevant tested choices: they recover 95.4% and 86.5% at 2.5 MS/s, with 1.20× and 1.31× CPU speedups. The more aggressive sparse schedules do not meet those hypothesis-coverage targets.

There are two different products here. A detection-oriented pass can use sparse or progressive searches, accepting a shorter evidence history. A full evidence/Doppler pass still needs sufficiently dense, representative observations; preserving a confirmation alone does not justify replacing that pass. The all-window four/six-candidate methods are useful intermediate options when hypothesis coverage matters more than the largest speedup.

Progressive search is attractive when preserving existence of a confirmation is the primary requirement, but it cannot cheaply reject receivers with no qualifying signal: they still consume all eleven searches. A fixed sparse schedule offers a predictable smaller workload at the price of missed confirmations. This explains why rate and signal mix change their relative performance.

The 2.5 MS/s stratum is particularly rich in detections: the original confirms all 32 receiver/visit pairs and finds positive evidence in 323 of 352 receiver/probes. Its large progressive speedup therefore should not be projected onto mostly empty scans. The other rates include 14 reference-unconfirmed receiver/visits in total and expose more exhaustive progressive work. Future admission testing needs sparse/weak detections and independently selected recordings, not just more repeats of these same visits.

No four-core speedup is multiplied into these single-core measurements. Combining process parallelism with reduced work needs a separate end-to-end measurement because IPC overhead and scheduling become more significant as each dwell becomes cheaper. No continuous real-time capacity or live deployment is claimed.

## Validation

The completed composite contains exactly 560 successful evaluations (10 methods × 28 visits × two repeats), with zero failed rows. Every method repeats its full scientific output exactly on all 28 visits. Fresh original outputs equal the previous frozen original on 28/28 visits. All 37 completed-run source hashes match, including the 36 predecessor sources and recovery runner. There are no unmatched added candidate hypotheses or positive candidates matched to reference-negative candidates in this experiment.

All 26 method, evaluator, deadline, and recovery tests pass. The custom complete-window implementation also passed a real saved-IQ parity smoke against the original before timing, in addition to mocked full-fold equivalence and the 96-pattern progressive confirmation property test. `summary.json` retains the complete independent scoring and repeatability checks; the generated tables retain both CPU and elapsed timings.

## Reproduction

Use the preceding benchmark's read-only extraction command if the local IQ cache is unavailable. Use a new output directory for every run.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 nice -n 19 .venv/bin/python reports/2026_09_28_ds7_glrt_progressive/run.py --inputs /tmp/leo-ds7-glrt-20260928 --output /tmp/ds7-progressive-new
.venv/bin/python reports/2026_09_28_ds7_glrt_progressive/evaluate.py /tmp/ds7-progressive-new --output /tmp/ds7-progressive-summary.json
.venv/bin/python reports/2026_09_28_ds7_glrt_progressive/tables.py /tmp/ds7-progressive-summary.json --output /tmp/ds7-progressive-results.md
.venv/bin/python -m pytest -q reports/2026_09_28_ds7_glrt_progressive/test_methods_sparse.py reports/2026_09_28_ds7_glrt_progressive/test_evaluate.py reports/2026_09_28_ds7_glrt_progressive/test_run.py
```

`SPEC.md` freezes the methods and measurement rules. `run-03/run.json` records the explicitly composite replay, runtime environment, source/input hashes and completion; `rows.jsonl` retains every result and timing. `summary.json` holds independent scoring, per-rate recovery gates, timing, and prior-baseline parity. `AUDIT.md` records the independent review.

The initial `run-01` was manually interrupted during its fifth visit when review found that a watchdog `TimeoutError` could be caught by per-call error collection instead of ending the experiment. Its partial rows, terminal incomplete receipt and exact runner snapshot are preserved and excluded from final scoring/timing. The runner now raises a dedicated `BaseException` deadline signal, covered by a regression test, so the terminal receipt is written and replay stops. No search-method code or parameter was changed for the restart.

`run-02` later received an external SIGTERM after 526 of 560 evaluations. Its cause is unknown, and the incomplete original receipt and raw rows are preserved. All 36 source hashes and the exact rotated row prefix were independently checked before recovery. `run-03` explicitly combines those unchanged 526 rows with the 34 missing evaluations in a new process; no completed row is replaced or selected by runtime. This affects the final 10 MS/s timing repeat through fresh process caches. The 2.5/5/7.5 MS/s two-repeat timings and all repeat-zero science were already complete before the interruption. The composite provenance is part of the reported result, not an uninterrupted-run claim.
