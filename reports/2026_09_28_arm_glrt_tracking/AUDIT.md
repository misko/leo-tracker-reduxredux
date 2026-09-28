# Independent evaluator and ARM harness audit

Scope: read-only review of `evaluate.py` and `arm_bench.py`; no hardware was
accessed. Review date: 2026-09-28.

## Validated behavior

- `match()` is a bipartite augmenting-path matcher. Each native positive has
  one owner and reassignment is allowed, so it computes maximum-cardinality
  one-to-one recovery under the stated `<=2` sample and `<=8 kHz` gates. The
  existing duplicate-credit test exercises the essential many-to-one case.
- Positives use the inclusive scientific gate `margin >= 0.025` on both sides.
  `baseline_positive_windows` counts baseline windows with any positive;
  `native_positive_windows` counts native windows with any positive; and
  `recovered_positive_windows` counts baseline windows with at least one
  one-to-one matched positive. Thus a native positive in a baseline-negative
  window is added evidence, not a recovered window.
- Baseline positives and baseline-positive windows are accumulated before the
  native-row lookup. A missing native window therefore remains in the
  denominator and contributes missed positives. Unexpected native windows do
  not enlarge that denominator.
- In the ARM path, `score()` sums `candidate_eval_attempts` and each window's
  `timings_ms.total_cpu`. The runner's fallback row already contains the failed
  tracking attempt plus refresh calls and CPU, so this correctly charges cold
  refreshes and fallback work once. Raw context/window/summary records are also
  retained for an independent accounting check.

## Concrete issues

1. **Host sweep is currently incompatible with the runner schema.**
   `evaluate.run.one()` passes every parsed JSONL record to `score()`. The
   runner emits context and summary records without `receiver_id` or
   `probe_index`, while `score()` indexes those fields unconditionally. A
   successful run therefore raises `KeyError` before producing an audit. The
   ARM harness avoids this by filtering `type == "window"` first.

2. **Failure accounting is not durable in either orchestration path.** A
   timeout, JSON decode failure, or worker exception escapes and can terminate
   the sweep; `arm_bench.py` also calls `check_returncode()` before writing a
   result. The planned denominator remains visible in the manifest, but no
   per-case audit with all sealed baseline windows is written. Error-status
   window rows are treated as empty candidates, which preserves the scientific
   denominator, but `score()` does not add an explicit `native_window_error`.

3. **ARM accounting is recorded but not cross-validated.** The harness does
   not assert 22 unique window rows, compare the summary attempt/CPU totals to
   the sum of window rows, or reconcile refresh/tracked/fallback mode counts.
   This does not change current score arithmetic, but a truncated successful
   output or future runner accounting regression could enter results with only
   `missing_native_window` errors and no hard qualification failure.

Recommended bounded fixes are to filter window records in the host path,
convert all execution/parse failures into a scored case with the full sealed
baseline denominator, flag non-`ok` rows, and assert row/summary accounting in
the ARM harness before marking a case complete.

## Post-run reconciliation

The completed ARM sweep and `summarize_arm.py` were independently checked
after the review above. The ARM accounting gap in issue 3 is fixed for the
published results: the summarizer requires all 22 unique receiver/window keys
per dwell, one summary, successful status, eight candidates per window, and no
scoring errors. It reconciles GLRT attempts, total CPU within 1 microsecond,
and refresh/tracked/fallback counts against the native summary.

An independent parse of all ten raw `refresh-*.stdout` files reproduced the
published totals directly from the sealed original baseline. Refresh intervals
1, 2, 3, 5, and 11 recovered respectively 46, 38, 28, 15, and 13 of 46
individual positives, and 26, 23, 18, 12, and 13 of 26 positive windows. CPU
seconds per dwell independently recomputed as 60.2165, 33.9969, 23.5426,
18.3021, and 7.75368. Raw records exactly equal the records embedded in
`results.jsonl`, and regenerating `summary.json` is byte-identical.

The ARM payload hash matches the copied build receipt, whose hash matches the
manifest. The static ARM runner is
`d6d4a9f6cb9d8dc4660d9c7b794a50ba3cc3f958522a6bc39cfd916b38fed855`.
The qualified host runner is a directly built ELF, and its bytes match its
receipt at `0ff1e61c3e92bfa9ffe7c292b121eb8ec32645f5425a797986c33d6f905c3b84`;
there is no delegation wrapper.

The scientific limits remain material: this is one invocation for each method
on only two metadata-selected 2.5 MS/s dwells, fallback was disabled, and no
variance estimate is available. The timing establishes CPU cost on that ARM
target, while recovery rates are small-cohort observations rather than a
general quality estimate. Issues 1 and 2 above still apply to the separate host
sweep orchestration and to retaining failed ARM invocations before a result is
written; neither affected these ten completed successful cases.

### Host harness clarification after successful sweeps

The executed host evaluator filters `type=window` records before scoring;
the original context/summary schema issue was fixed before the completed
64- and 704-dwell runs. Failure-durability remains a limitation of this
experimental harness. The completed runs have complete expected inventories
and no scoring errors, so this limitation does not change their denominators.
The maintained scorer also passes an adversarial augmenting-path test that
would fail with greedy matching (three scorer tests pass).
