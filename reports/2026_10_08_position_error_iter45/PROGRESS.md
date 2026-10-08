# Completion checkpoint: retain running jobs

The unlimited goal is active. Do not restart live jobs, mark the goal complete,
or replace the frozen candidate with diagnostic oracle results.

The first published summary was a checkpoint: DS18 34/34, DS17 51/51, DS16 50/63.
DS18 fitted-c mean is 2.739331 km versus baseline 4.422188 km. The newly included
DS16-046 has a 265.789353 km candidate error, making the current DS16 50-member
candidate mean 6.342566 km. All remaining members stay in coverage denominators.

Two live resumable completion jobs remain in the `leo-hard60-default` worktree;
the second original lane has finished:

- exec session `73048`, Python PID `3985160`: original completion lane starting
  DS18-033, DS16-001, DS16-009, DS16-013, DS16-023, DS16-041, DS16-045,
  DS16-047, DS16-055.
- Completed exec session `86438`, former Python PID `3985173`: original lane starting
  DS18-034, DS16-008, DS16-011, DS16-015, DS16-034, DS16-042, DS16-046,
  DS16-050.
- exec session `58997`, Python PID `3985901`: frozen setup-failure retries,
  DS18-034, DS16-001, DS16-008, DS16-011, DS16-015, DS16-034, DS16-042.

Poll these handles or check processes before any new invocation. The isolated
baseline root is `local/standard-baselines`; it was initially absent, causing
seven pre-fit failures. First attempts are retained in `results/`, retry outputs
in `retry/results/`. The directory now exists. Completed original cases include
DS18-033, DS16-009, DS16-013, DS16-046 and DS16-050; the DS18-034 retry also completed
successfully. DS16-001's retry baseline is complete and its candidate is running.
The next published snapshot includes at least 52/63 DS16 members; use summary.json
for exact current checkpoint metrics, not the initial 50-member figures above.
Each baseline invocation is limited to four resumable 500-second slices. Preserve
pending slice receipts; do not label a checkpoint timeout an input exclusion.

The executed numerical sources and protocols are immutable. The frozen
`summarize_completion.py` can be rerun as receipts arrive; every published Git
commit preserves the earlier report snapshot. It combines iteration44's 131
results with completion receipts, resolves setup retries, and reports all 148
members, dataset-specific metrics, historical/completion subgroups, c ablations,
frequency RMS, paired regressions and convergence/fallbacks.

Iteration46 is a separate completed DS18 common-bank/shared-clock diagnostic:
eight fits, four converged zero-c fits, all four fitted-c fits nonstationary
despite optimizer success. It does not change benchmark values.

Iteration47 audits DS16-046: the correct region was sampled at 5 km resolution
but discarded before final fitting. A good nearby coarse point ranks 13th;
12.5/25 km separation retains only distant regions. Post-hoc 40/50 km separation
retains the correct neighborhood. The next useful diagnostic is complete fitting
of an additional 50 km-separated region set while preserving original choices,
with matched c arms and unchanged likelihood, followed by score-based selection.
This is not yet a proven correction. DS18's common-bank zero-c likelihood still
prefers its distant solution even after optimization.

No production settings, published contracts, golden fixtures, QNAP data or RF
collection changed. Preserve hard60 bounded recovery, fitted-c default and
longest-16-track PNG rendering. No new RF collection is authorized.
