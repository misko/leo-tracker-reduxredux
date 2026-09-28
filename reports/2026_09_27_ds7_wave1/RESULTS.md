# DS7 bounded evaluation results

The first frozen single-recording baseline is **4,004.26 m** from the operator-supplied reference; the two-recording joint fit is **3,638.94 m**. Both converged inside the declared bounds. Two executions of the final single-recording code produced identical predictions and diagnostics. These are overlapping repeated-site units, not a corpus-wide accuracy estimate. Neither meets the sub-kilometre target. The reference is unsurveyed and prior research exposure is unaudited.

The coordinator scored the sealed prediction only after freezing the model, inputs and output. Scores were not sent to model workers for tuning. No RF was collected, no source recording was changed, and no raw IQ has been read in this evaluation wave.

## Executed evidence and decisions

| Direction | Evidence | Decision |
|---|---|---|
| A: corrected baseline | Single: 56 tracks, 2,391 observations, 4,004.26 m. Joint prefix2: 115 tracks, 3,638.94 m, 56.97 seconds. Both converged and interior | Hold prefix4/8 preparation: prefix2 consumes nearly all of the 60-second per-unit budget. Larger units are unattempted, not scientific failures |
| B: orbit inputs | All-archive Space-Track selection retains all 11,119 objects and updates six shortlisted objects in 26 slots. Final A/B predictions are identical; position changes only 0.0142 m and error is 4,004.27 m | No meaningful smoke improvement; hold expansion. SupGP/provider ephemerides unavailable; HF lacks matched coverage |
| C: receiver clock | Receiver-constant column adds no rank beyond 56 per-track offsets: rank 56/57. Centered drift survives offset-only projection but has no independent physical bound or full position/nuisance identifiability evidence | Reject redundant constant bias; hold drift fitting |
| D: orbit hierarchy | Three leading candidates repeat across disjoint donor/target groups; zero qualified independent identity/calibration priors | Stop hierarchy fitting at its admission gate |
| E: association/search | Local control exactly reproduces baseline using 42 evaluations in 29.59 seconds. Multibasin search reaches the 60-second limit with no response | Stop expansion under this budget; preserve the failed attempt. Fix privileged-child cleanup before future execution |
| F: CFO extraction | Four-rate panel frozen before scoring; its 10 MS/s member is bound to the second baseline export | Hold extraction until native-window, timing, pilot/alias and matched-epoch evidence is available; no IQ or downstream improvement claim |

## Baseline reproducibility

- [Scored final prediction](coordinator/baseline-smoke-score-v1/scores.json), [final run A](baseline/smoke-final-a-v1/results.json), [same-code replay B](baseline/smoke-final-b-v1/results.json).
- Final runs took approximately 24 seconds each, with 42 total objective evaluations across three starts. The runtime is recorded in the response, separately from the coordinator runtime.
- [Pinned numerical oracle comparison](baseline/pinned-oracle-audit.json): six real frozen tracks, objective differences at most 1.36e-11 and gradient differences at most 5.19e-7 at the two audited points.
- [Exact orbit check](baseline/exact-orbit-audit.json): maximum interpolation discrepancy at the solution is 0.007251 Hz.
- Earlier solver and optimized-port runs use different code hashes. Their agreement is implementation comparison evidence; final A/B supply the same-code deterministic replay.
- The original admission-only run is retained as unavailable and is not counted as a scientific baseline prediction.
- [Two-recording score](coordinator/baseline-prefix2-score-v1/scores.json) and [sealed prediction](baseline/prefix2-solver-v1/results.json): 49 total evaluations, 115 tracks, converged/interior. This run has not received its own deterministic replay.

## Search and execution limits

[Association execution evidence](association/EXECUTION.md) separates the successful local control, an initial timing-grid configuration failure, and the repaired multibasin attempt that timed out. The [local score](coordinator/association-local-score-v1/scores.json) is exactly the baseline score; the [multibasin score receipt](coordinator/association-multibasin-score-v2/scores.json) retains one failed attempt with no error estimate. The synthetic physically wrong trajectory loses 41.51 log-likelihood units; candidate-row permutation changes the mixture objective by zero, as it should.

The multibasin timeout exposed a runner defect: its privileged child survived the unprivileged process-group cleanup. The coordinator killed that exact owned process after observing it at 88 seconds, verified no late response or seal change, and repaired admission of launch commands. The runner now rejects explicit privilege/session wrappers. Future adapters must use the runner's UID and process group; the orbit comparison uses a privileged runner and direct interpreter. [Repair receipt](coordinator/cleanup-repair.json). Thus the failed search's 60-second receipt records the runner's wait budget, not a claim that actual computation stopped precisely at that time.

## Direction receipts

- [Orbit inventory and limitations](orbits/README.md), [fixed-roster alternatives](orbits/first-session-fixed-roster-audit.json), and [original-policy reproduction](coordinator/original-orbit-policy.json).
- [Matched orbit comparison](orbits/matched-comparison.json) and [coordinator score](coordinator/orbit-comparison-score-v1/scores.json). Preparation took 73.85 seconds and final fits approximately 22 seconds each. All unaffected bank rows are byte-identical; strict `start - 505 s` archive causality is preserved. Error changes by +0.0127 m, which is immaterial here. The earlier completed privileged-wrapper run remains recorded separately and excluded from the final comparison.
- [Clock admission report](clock/REPORT.md). Its initial missing-bank observation predates the later bank export; the unresolved constraints and full identifiability requirements still apply.
- [Orbit-hierarchy report](orbit-hierarchy/REPORT.md).
- [Association specification](association/SPEC.md) and [structural gate](association/gate-receipt.json).
- [CFO panel](cfo/panel.json) and [preparation report](cfo/README.md). An unavailable tracking product is not evidence of a failed raw capture or absent RF signal.
- [CFO handoff](cfo/handoff-0001.json) binds the selected 10 MS/s member to its baseline observation export and specifies the native-window and acquisition evidence still required. Sample rate alone does not establish known-pilot applicability.

The CFO and hierarchy endpoint inventories were taken at different times. Two products completed between those snapshots; their receipts retain their original observations rather than silently refreshing the frozen panel.

## Repository entry points

`tools/ds7_eval.py` owns validation, reference-free requests, bounded execution, sealed predictions and coordinator scoring. `config/ds7/` contains planned direction specifications and separately named executable ready arms. `tools/ds7_baseline_adapter.py` and `tools/ds7_export_baseline.py` implement the baseline path; direction-specific tools and component tests live alongside them under `tools/` and `tests/research/`.

The DS7 mint remains in `reports/2026_09_27_ds7_post_ds6/`, prepared suites in `reports/2026_09_27_ds7_evaluation_setup/plans/`, and this wave's receipts here. Large orbit-state banks and archived provider payloads are local ignored artifacts under `.leo/ds7-wave1/`; receipt hashes bind them, but a fresh clone must reproduce or recover those bytes before replay.

## Priorities after this wave

1. Make the frozen baseline and wider search fit credible per-unit runtime budgets, preserving numerical equivalence. Then complete the predeclared 1/2/4/8 panel and independent-fit aggregation controls before ranking models across groups. The current two-recording improvement is one overlapping comparison, not a support-scaling law.
2. Test association completeness and explicit null/outlier hypotheses under matched compute after the runtime gate. Local search reproduces the same solution, while the wider search is unqualified; this wave does not show that search is complete.
3. Complete the small CFO panel's native-window and pilot/alias handoff, then compare measurements at identical epochs. Existing track exports alone do not support a valid extractor comparison.
4. Admit receiver drift only with full position/nuisance identifiability and independently defensible constraints. Constant receiver offsets remain redundant.
5. Keep the tested GP-freshness variant low priority unless broader evidence warrants revisiting it. Its first-session position change is negligible, and unavailable higher-grade products cannot be evaluated retrospectively by substituting current data.
6. Hold orbit-error transfer until qualifying repeated-identity support and independent priors exist. Candidate repetition alone is insufficient.

These are work priorities, not a statistically established ranking of all model families. No tested smoke result is below 1 km. Prefix4/group8, eleven-group and full-88 scientific evaluation have not run; independent-fit averaging controls and real-IQ extractor comparisons have not run. No multi-hour campaign was launched.

## Closeout validation

The complete DS7 component suite passes: **52 tests** in the recorded scientific runtime. Ruff passes for every `tools/ds7*.py` and `tests/research/test_ds7*.py`; `git diff --check` passes. The minted DS7 verifier still passes all seals, exact 88 approved recordings, DS6 exclusion, accounting, pose bindings and evaluation units. Direction receipts preserve unavailable, failed and timeout attempts rather than removing them. CPU/RAM limits are declared coordination budgets; this wave does not provide measured peak-memory accounting for every process.
