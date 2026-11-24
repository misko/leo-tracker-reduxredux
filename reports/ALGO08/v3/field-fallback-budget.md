# What the fallback costs on the first 24 DS30 field pairs

The candidate fell back to the ordinary solver on **one of 24 recordings**, DS30-0147. That was the only recording on which it took longer than ALGO08v3. The other 20 fixes completed through the lean solver, and three recordings were withheld before a solver ran. Skipping the failed proposal on 0147 with perfect foresight would increase aggregate wall speedup from **1.644× to 1.664×**. Even giving away both the failed proposal and its replacement solve on that recording reaches **1.742×**. [Frozen scope](field-fallback-budget-protocol.md) · [Machine-readable measurements](measurements/field-fallback-budget-first24.json)

| Timing scenario, all 24 paired recordings | Wall removed | CPU removed | Summed wall speedup | Median paired wall speedup | Seconds over half the installed total |
|---|---:|---:|---:|---:|---:|
| Both original executions | 0.00 | 0.00 | 1.644× | 1.739× | 240.55 |
| Skip the failed lean proposal | 16.47 | 16.21 | 1.664× | 1.739× | 224.08 |
| Make the fallback call instantaneous | 59.33 | 59.09 | 1.720× | 1.750× | 181.22 |
| Remove both measured calls | 75.81 | 75.30 | 1.742× | 1.750× | 164.74 |

The last three rows are sensitivity calculations. They hold the terminal decision, accuracy, acquisition, remaining solver work and publication times fixed. The timed fallback supplies the accepted fix on 0147. Its scientific result cannot be inferred from the rejected proposal. The two measured calls cover at most **31.5%** of the 240.55 s aggregate gap. Removing the failed proposal alone covers **6.8%**. The observed lean successes had 1.714× summed and 1.718× median paired speedup. Reaching 2× therefore requires savings on the common path.

| Observed candidate route | Pairs | ALGO08v3 / candidate fixes | Within 1 km, fixed-zero | Within 1 km, fitted | Within 2 km, both arms |
|---|---:|---:|---:|---:|---:|
| Lean solver completed | 20 | 19 / 20 | 12 / 9 | 14 / 10 | 19 / 17 |
| Lean proposal rejected, ordinary fallback | 1 | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |
| Withheld before inference | 3 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

On 19 shared fixes in the lean-success group the median paired change was **+473 m** at fixed-zero calibration and **+316 m** with fitted calibration. On DS30-0147 the candidate’s final errors **decreased by 534 m and 362 m** relative to the installed build. These are comparisons between complete algorithms on the same recordings. They cannot establish what a shorter fallback would publish. [Case-level clocks, calibration results and package verifier](field_fallback_budget.py)

The scorer checks the original enrollment and relocation seal, the two selected process receipts and the successor’s native, terminal and stage identities. It reuses the official scorer for positions, wall ratios and CPU ratios. On the fallback route the pre-evidence timer ends before the ordinary fallback timer starts. Each nested stage is charged once. The three pre-solver withholds retain their actual end-to-end clocks. [Instrumented solver boundary](blind_joint_route.py) · [Route and budget tests](../../../tests/pipeline_eval/test_field_fallback_budget.py)
