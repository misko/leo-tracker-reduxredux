# Where a second 2× could come from after DS30-0402

The best combined comparison from original samples through exit is **12.108 → 9.075 s on two warm DS30 recordings**. That is 1.33× by total time. One recording produced a fix and one withheld. The new 3.09× result starts at saved detections on a particularly expensive solve. It identifies a promising optimization target, while a second end-to-end doubling still needs faster acquisition. Named ALGO08v3 is the comparison throughout. [Raw comparison](unified-short-layout.md) · [Saved comparison, errors and historical rank](phase-route-challenge.md)

## How much each stage needs to save

The first 55 archived v3 processes include 52 completed fixes with three wall clocks. On these 52, launch through sealed detections accounted for **3,663.3 s (67.1%)**, detections through the terminal decision **1,644.6 s (30.1%)**, and terminal through publication and exit **150.6 s (2.8%)**. The corresponding stage medians were 72.62, 30.66 and 2.81 s. These clocks include waiting and startup within their boundaries. The other three recordings have a complete process clock only. The all-55 calculation charges each of those its full measured time. [Sealed stage data](measurements/acquisition-throughput.json) · [Clock definitions and sensitivity model](retained_wait.py)

| Hypothetical change | Median paired ratio, 52 fixes | Ratio of totals, 52 fixes | Median paired ratio, all 55 | Ratio of totals, all 55 |
|---|---:|---:|---:|---:|
| Eliminate detections-to-terminal time entirely | 0.7081 | 0.6987 | 0.7134 | 0.7083 |
| Halve both acquisition and detections-to-terminal time | 0.5133 | 0.5138 | 0.5135 | 0.5293 |
| Cut acquisition by 50% and detections-to-terminal by 60% | 0.4864 | 0.4837 | 0.4873 | 0.5001 |

Each estimate sums the three scaled wall clocks within each recording, with terminal-to-exit charged in full. Both ratios must be at most 0.5000. The third example narrowly misses on all 55. It also assumes gains in elapsed time. Granting the same reductions only to CPU work and retaining observed wait gives an all-55 summed ratio of **0.614–0.644**, depending on which stages incurred the waits. These historical process clocks cannot distinguish storage stalls from scheduling delays. A warm kernel benchmark alone cannot establish the needed wall saving. The 55 recordings and these scenarios are engineering budgets. They have no new accuracy measurements.

To reproduce the table from the repository root, run the following with the repository Python environment. The command reads the existing clocks only.

```sh
PYTHONPATH="$PWD:$PWD/src:$PWD/reports/ALGO08/v3" python - <<'PY'
import json
from pathlib import Path
from retained_wait import gates

ledger = Path("reports/ALGO08/v3/measurements/acquisition-throughput.json")
rows = json.loads(ledger.read_bytes())["rows"]
fixes = [row for row in rows if row["stages"][0] > 0]
for acquisition, solve in ((1, 0), (0.5, 0.5), (0.5, 0.4)):
    print(acquisition, solve, gates(fixes, acquisition, solve, "scale_elapsed"),
          gates(rows, acquisition, solve, "scale_elapsed"))
for allocation in ("best", "worst"):
    print(allocation, gates(rows, 0.5, 0.4, allocation))
PY
```

## Ranked experiments

DS30-0402 spent **31.96 CPU s** evaluating three satellite-family alternatives. All three were rejected. DS30-0155 never invoked that stage. On 0402 the repeated residual-noise screens took 8.49 profiled seconds within the larger stage. A prototype that keeps the original least-squares calculation reduced median per-screen CPU from **58.1 to 37.1 µs** on 12 sampled track supports. All sampled diagnostics matched using residuals constructed from the saved frequencies. Extrapolating to the eligible inner calls yields **about 1.73 CPU s**. The remaining time includes constrained optimization and other checks. Retaining the original acceptance rules is important on cases where a reassignment succeeds. [Profile and microbenchmark](named-roster-0402.md)

The first three experiments address different bills. Their timings must be measured in one executable before adding the savings. Each proposal uses measured signal, orbital state, or runtime inputs available by the time of the decision. Surveyed truth is reserved for scoring.

| Rank | Direction | Cheapest informative experiment |
|---:|---|---|
| 1 | **Revised acquisition design. Schedule useful work during input waits.** Deliver authenticated blocks into a bounded queue, and use the single compute core for already-ready receiver or orbit work while the next read is outstanding. | Intersect measured stalls with independently ready work and report the maximum seconds that can overlap. Charge memory, all reads and both digests. Only then time reversed-order pairs with comparable initial residency. Earlier read-ahead and decoder microbenchmarks gave mixed whole-run results. [Input timing](dense-ingress-attribution.md) · [Decoder experiment](zstd-assembly.md) |
| 2 | **New solver priority. Make the original satellite-family checks cheap.** A family trial asks whether a group of tracks fits another satellite. Preserve the tracks, both calibration arms and every acceptance threshold. Move invariant inputs to the residual-noise check outside its optimization loop. | On 0402 each of 401 gate evaluations screened 209 tracks. Verify every scalar against the original, then compare a complete rejected reassignment and a case where a reassignment is accepted. A faster least-squares implementation can change subsequent optimizer visits. [0402 stage profile](named-roster-0402.md) · [0155 with no family trial](named-roster-0155.md) |
| 3 | **Revised receiver. Escalate uncertain timing proposals before expensive verification.** A cheap within-window scout proposes timing. Run the original search immediately on ambiguous lanes and retain independent secondary-signal search. | Freeze the confidence statistic before opening a held prefix. Include missed factors, false positives, routing and full retries on both antennas. An ideal four-row shortlist projected 4.50 s gross on dense, while the measured one-lag scout lost 7 of 44 published factors. The narrow 3.67 s ideal early-escalation ceiling on that scout leaves very little margin. [Oracle](timing-only-oracle.md) · [Measured scout and retries](short-timing-lags.md) |
| 4 | **New solver priority. Extend the compiled likelihood to the frequent fallback shapes.** The 0402 profile recorded 239 unsupported likelihood calls across four array shapes, charging 8.05 CPU s. | Capture one instance of each shape. Identify the reason for fallback, then time the eligible ones against the original objective and gradient in both arms. The entire 8.05 s is an upper bound. A matching shape alone cannot prove that the underlying calculation is the same. |
| 5 | **Revised solver architecture. Keep v3's observation selection and swap in faster fitting pieces.** An earlier fit can initialize the next one. Stable observations and orbital inputs can be shared across trial fits. | On 0155 the choice of observation list mattered far more than which fitter consumed it. A real warm start preserved every assignment on both 0155 and 0160, with 1.61 s and −0.03 s of whole-process savings. Time each addition on a case with a different selected assignment or a history retry. [Crossover](cross-roster-0155.md) · [Warm transfer](causal-pre-refit-0160.md) |
| 6 | **New alternative to dropping receiver visits. Compute cancellation updates from shared linear intermediates.** Subtract the canceled primary signal's response from already computed correlations where the transform is linear. Recompute affected quantities when integer rounding, clipping or normalization changes the result. | Measure what fraction of receiver CPU is both reached on second scans and reusable. Compare intermediate values, signed secondary detections and continuation state against the full residual search. Stop if that fraction is small or exact corrections cost the saved transform. |
| 7 | **Revised adaptive measurements. Choose extra observations where two live satellite assignments predict distinguishable frequencies.** Keep independent coverage on both radios for a previously unseen signal. | Compare against equal-cost uniform scheduling on saved visits. Charge the ensuing solve. A simpler recent-positive policy projected 2.99 s of receiver savings and added 6.38 s to the dense solver. Require both calibrated position results and the withheld cases. [Dense purchase and downstream cost](causal-mask-dense.md) |
| 8 | **New solver control flow. End a family trial when a terminal condition makes it ineligible.** Both arms must pass to replace the incumbent. Execute downstream work lazily once further rescue is provably impossible under the original rules. | Trace *when* a terminal veto becomes available relative to the expensive work. Count remaining calls and required diagnostic fields. Price zero savings on trials with no early proof. Replay an accepted counterexample before using it in the full solver. |
| 9 | **Revised fast path for short recordings. Combine the existing early withholding proof and cheaper drawing with deferred initialization.** | Compare a fresh-process fix and withdrawal. Verify both decisions, grid, published diagnostics and all eight decoded images on a fix. Rendering already accounts for much of the weak saved-input improvement, so time the combination only once. [Weak exact control](named-weak-exact.md) · [Raw pair](unified-short-layout.md) |
| 10 | **From scratch for future captures. Make each visit independently verifiable and seekable.** A receiver could then pay for exactly the visits it needs while retaining raw I/Q for later analysis. | Write a small experimental index for a saved member and time both construction and reading. Test detection of corruption, omission and reordering. Report legacy DS30 conversion and a future capture-time design separately. [Existing signed input requirements](authenticated-input-coverage.md) |

**Triage order.** Start with the wait-overlap ceiling and the original family gate. Check the receiver escalation budget on saved weak and dense prefixes before another raw pair. Then combine only changes that preserve the decisions on a typical fix, a withdrawal and an ambiguous recording. Freeze the build and test a geographically separate containing and missing offer before expanding DS30. The historical India simulation already exposed a false fix just 1.5 km outside the offer in both solvers. All DS30 physical recordings come from one roof. Confirm both zero and fitted calibration, returned-fix coverage, horizontal error distribution and eight required figures. Keep Gauss to one low-priority benchmark at a time. [Geographic control](india-cumulative-transfer.md)
