# Racing the three full-catalogue cold finalists

The full-catalogue finalist race reduced the complete dense DS30-0008 saved solve from **28.818 to 23.482 CPU seconds** and preserved the winning score, both calibration arms, 4,440 owners and roles per arm, and all 179 grid nodes. Timing the three finalist fits separately attributed **4.450 CPU seconds** of savings to completing only the leader. The three saved pairs establish numerical parity on their inputs. They provide no bound on the winning assignment in another recording. [Frozen protocol](cold-finalist-race-protocol.md) · [Paired timing and equivalence](measurements/cold-finalist-race-summary.json)

## Shared work and decision rule

The dense finalists share all 111 track fragments. Ranked pairs 1/2, 1/3 and 2/3 assign the same satellite and integer alias on 81, 102 and 87 fragments respectively. The fitted states still couple tracks through the joint phase posterior, which depends on the branch's entire design. Earlier replay on the India capture found no identical native fit inputs between branches and only 6.780 ms of exact rank-to-fit reuse. A sampled-observation selector changed 65 owners on DS30-0374 and led one tested exterior offer to publish. The earlier screened stock route completed two full phase refreshes on every finalist before taking a leader through its remaining three. This trial holds the full causal catalogue, ordered nodes, all observations and the objective fixed, and starts the comparison within the first refresh. [Earlier exact-input audit](../single-core-2x/solver-initial-prefix.md) · [Earlier sampled selector](../single-core-2x/solver-sampled-initial.md) · [Earlier two-refresh screen](../single-core-2x/solver-stock-finish-protocol.md)

Each finalist pays for two outer iterations of the installed bounded secant optimizer with a fixed-zero initial phase reference. An interior, finite leader must beat each other point by more than 1% of its own partial score and four times the greater of their most recent objective drops. Ambiguous, invalid or boundary cases complete all original fits. A paused optimizer retains its position, trust radius, Jacobian and evaluation count. Each completed finalist still gets the full second phase refresh. The prefix objective supplies no bound on later improvement or the refreshed objective. [Paused optimizer and race](cold_finalist_race.py)

## Matched results

| Saved input | Cold CPU s, control → race | Complete CPU s | Complete elapsed s | Completed finalists | Owners per arm / grid nodes |
|---|---:|---:|---:|---:|---:|
| DS30-0008 complete | 12.127 → 7.479 | 28.818 → 23.482 | 28.855 → 23.484 | 3 → 1 | 4,440 / 179 |
| DS30-0016 paid quadratic | 0.304 → 0.226 | 2.516 → 2.497 | 2.516 → 2.497 | 3 → 1 | 36 / 179 |
| Southern public simulation, paid quadratic and containing offer | 0.323 → 0.337 | 2.935 → 3.009 | 2.936 → 3.009 | 2 → 2 | 118 / 165 |

Dense control scores after both refreshes were 30,650.1768, 31,365.6883 and 31,640.2828. The race compared 31,153.0835, 31,523.0595 and 31,949.6257 in the first refresh. Its closest gap was 369.9759 and the rule required 311.5308. The physical short case had a 63.0311 closest gap against 3.4214 required. The southern case had only two ranked hypotheses and exercised the complete-fitting fallback. All three pairs chose the same node, final score, position and phase references as the control. The full ordered rank, RF fits, supported observations, owner/role rows, both full numerical grids, paths, qualification and exterior decisions also matched exactly. Both small packets' input identities match after removing the separately measured detector reselection clock. [Run records and decision checks](measurements/cold-finalist-race.json.gz)

The dense control spent 5.083 CPU seconds ranking, 1.794 completing its leader and 0.992 plus 4.203 on the two losers. Omitting the losers for free would save 5.195 seconds for a **1.220×** saved-solve ceiling at those control timings. The race paid 0.738 seconds for the losing prefixes. Total finalist CPU dropped from 6.990 to 2.540 seconds. Observed complete saved-solve speedup was **1.227×**. Ranking and numerical evidence were 0.196 and 0.210 seconds faster with identical work in that process, so the full clock difference overstates savings attributable to the race. No end-to-end recording speedup was measured. The southern result retains the older sparse receiver's fixed-zero position error of 1.261 km, compared with 0.817 km from complete-receiver v3. [Independent full-receiver comparison](full-family-south.md)

## Reproduce

Use an empty directory and run `cold_finalist_race_trial.py run CASE MODE OUT` in six separate processes, with `CASE` set to `DS30-0008`, `DS30-0016` and `south-containing`, and `MODE` set to `control` and `race`. Use `compare DIR SUMMARY FULL` once all processes have finished. The runner verifies the sealed complete/paid receiver packets and causal archive and records the selected rows, both calibration arms, grid evidence and qualification. These clocks cover the complete saved solve including its numerical grid. Acquisition and PNG rendering are outside that scope. Twenty-two focused and adjacent tests passed. [Trial runner](cold_finalist_race_trial.py) · [Full receipt](measurements/cold-finalist-race.json.gz) · [Component tests](../../../tests/pipeline_eval/test_cold_finalist_race.py)

The first dry run paused the repository default optimizer, while the installed route binds a compact secant solver wrapped in endpoint reuse. The next precheck rejected the wrapper and invoked the installed fallback. Both attempts are excluded from the comparison. The measured candidates use the correct pinned wrapper and ran after the retained fresh controls. The frozen budget and margins were unchanged. The measured finite-path refiner SHA-256 is `f8c170808ec14d7c5bfa5780b779db368710f01e1ff85807cb4facd27cb89a38`. The checked-in refiner also records nonfinite prefix diagnostics as JSON null when the existing invalid-input fallback is triggered.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 65s \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  OMP_THREAD_LIMIT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/cold_finalist_race_trial.py \
  run "$case" "$mode" "$output"
```
