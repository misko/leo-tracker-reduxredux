# Scanner workload and the 10x objective

The latest completed goal turn made progress: paired SIMD validation and
parallel replay produced new evidence. Neither establishes a 10x reduction in
complete detector cost. General compute work continues without radio access.

## Distinct workloads

The existing native experiments rank six windows and confirm one ranked window
per receiver. In contrast, `src/leo/scanner/detector.py:analyze_glrt64_dwell`
evaluates the entire overlapping probe schedule and returns every retained
candidate response. `src/leo/cli/composition.py` configures ten retained
candidates, whereas the configuration model's standalone default is eight.
For a 120-ms dual-receiver dwell, the configured scanner therefore executes:

- Eleven 20-ms probes at 10-ms stride for each receiver: 22 acquisitions.
- Up to ten candidates per acquisition: 220 GLRT confirmations.
- Eleven scientific coarse CFO hypotheses per acquisition: 242 coarse rows.
- For an interior coarse CFO basin, up to 321 fine CFO hypotheses and 41
  conditioned hypotheses per retained candidate. Boundary clipping can reduce
  these counts; unsupported candidates can reduce confirmation count.

These are source-derived upper bounds, not measured execution counts or timing.
The probe schedule, candidate ranking, exact/control scores and first-confirmed
decision are part of the scanner comparison. Replacing this work with the
one-confirmation native experiment would change the workload; its timing cannot
be presented as an equivalent application speedup.

The repository scanner analysis path is a useful application benchmark. It is
not proof of the currently deployed adaptive DS5 detector: the local
`tools/run_adaptive_capture_cycle.py` uses `Ci16EnergyDetector`. No live deployment
configuration is changed or inferred from this benchmark.

## Bounded next measurement

Profile complete scanner analysis on the first manifest-ordered physical visit
at each supported sample rate in the already frozen new-development inventory.
Use both receivers and ten candidates, and report actual candidate counts and
selected native backend. Keep profiler attribution separate from uninstrumented
whole-call CPU/wall measurements. Record thread settings and CPU affinity.
This two-visit diagnostic selects optimization targets; it is not a new
scientific qualification dataset or a replacement for the 320-case suite.

Input conversion belongs in any subsequent end-to-end candidate comparison.
No stale IQ result may stand in for analysis of a fresh capture. Reusable
template geometry and arithmetic workspaces are independent from cached
channel hypotheses, which require separate fresh-evidence and discovery tests.

Any 10x claim must name its original baseline and matching output contract,
retain scientific coverage, and measure the complete candidate call against
that baseline. Server throughput, live decision latency and CPU work remain
separate quantities. Existing failed experiments and unopened holdout remain
unchanged.

## First measured application profile

`application_profile/results.json` completed both selected visits. The native
acquisition backend was `avx2_fma`, numerical thread environment was one thread,
and execution was pinned to performance core 0. Each call actually performed
22 acquisitions and 220 GLRT scores. Uninstrumented, first-use calls measured:

| Rate | CPU | Wall |
|---|---:|---:|
| 2.5 MS/s | 1,558.7 ms | 1,615.5 ms |
| 5 MS/s | 4,131.7 ms | 4,143.1 ms |

The separate instrumented calls returned the same decision outputs. Acquisition
accounted for 81.5% and 93.0% of diagnostic CPU respectively; the coarse grid
alone accounted for 44.4% and 68.5%. These are nested inclusive diagnostic
fractions, not additive exclusive times or a steady-state speedup. Both returned
a first detection on probe 0 and evaluated the full schedule. The subsequent
early-exit diagnostic measured actual confirmation at probe 2 for 2.5 MS/s and
probe 5 for 5 MS/s. The prior claim that both confirmed at probe 2 incorrectly
inferred confirmation time from the returned earlier hit.

This changes the immediate optimization priority: the application coarse
timing/CFO grid is the largest measured target. Compacting the GLRT workspace
can remove allocation waste, but its entire measured workspace stage is only
12.0% and 4.7% of these diagnostic calls. It cannot alone close the 10x gap.
The full-response contract and decision-only early-exit option are distinguished
in `application_profile/CACHE_SEMANTICS.md`.

## Compact workspace result

The isolated compact 64-symbol workspace passed exact full-response comparison
against the unchanged scanner, including all 22 probe rows and their candidate
fields. Three paired repetitions after warmup, with input conversion included,
measured 1.051x CPU speedup at 2.5 MS/s and 0.999x at 5 MS/s. This removes real
allocation waste but does not provide a consistent material application gain.
See `application_compact/VALIDATION.md`. Production sources remain unchanged.

The next acquisition experiment is specified in
`application_profile/COARSE_GRID_AUDIT.md`. Its overlap-reuse ceiling alone is
only about 1.25x/1.45x whole-call speedup. Reaching 10x still requires a larger
reduction in acquisition work, potentially a new detector architecture with
explicit fresh-signal discovery and false-positive validation. Bit equality is
the gate for exact implementation replacements, not a prohibition on evaluating
new scientifically validated algorithms.

Full research-suite validation: 268 tests and 11 subtests pass. The suite now
binds the current checkout's `leo` package before collection, so older research
scripts adding numerical-reference checkout paths cannot redirect application
imports. Frozen benchmark source locks and result receipts were not changed.
The profile and compact standalone runners already pinned the correct current
checkout sources; the issue was combined pytest collection, not their timings.

## Subsequent measured progress

The alternative coarse correlators preserved score maps to within 7.8e-16 and
peak indexes exactly, but NumPy correlation and FFT routes were substantially
slower than the existing AVX2 kernel. Their frozen performance gate failed;
no full-recording claim followed. See `application_coarse_alternatives/REPORT.md`.

An exact decision-only early return measured 3.874x/1.761x CPU on the two positive
cases; actual work stopped after probes 2/5. Both zero controls ran the entire
negative schedule. Its declared 3x gate at both rates failed, although the exact
smaller gain remains potentially useful. See `application_early_exit/REPORT.md`.

The full-response parallel prototype preserves all 22 probe rows and all
candidate fields. Eight performance-core workers reached 6.61x/7.04x lower
single-dwell wall latency. Twenty-two workers, including efficiency cores,
reached 8.20x/10.69x, at the cost of 43%/29% more aggregate CPU. Latencies were
168.92/373.45 ms, still above the 120-ms capture duration. This is genuine
within-dwell latency evidence rather than batch throughput, but it is only two
development cases and does not establish the full 10x objective. See
`application_parallel/REPORT.md`.

The next detector architecture is specified in
`application_coarse_alternatives/TRACK_GUIDED_DESIGN.md`: fresh guided
confirmations with all-window blind fallback, causal state and explicit new
signal/false-positive tests. It deliberately has a different candidate inventory
and requires scientific decision qualification; it cannot claim equivalence to
the complete 220-score report or inherit native detector qualification.

The combined suite now passes 307 tests and 11 subtests. Frozen early-exit tests
are collected through a small import-isolation adapter because their historical
generic module names collide with prior experiments. Their original files,
source locks and measured receipts are unchanged.
