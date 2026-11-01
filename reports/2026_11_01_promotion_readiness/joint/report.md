# Two simultaneous whole-family replacements: bounded development diagnostic

Neither worst case is improved by an accepted hypothesis. The original ALGO06 fallback remains exact: DS26-0203 fitted-c error **6.858 km** and DS26-0070 **6.716 km**. This is a negative development result, not a population validation or promotion recommendation. All identities and fits use the existing causal 72-hour catalogue; no later TLE or evaluation position enters nomination, ranking, calibration, starts, or acceptance.

There is one useful methodological finding: the admissible DS26-0070 pair passes joint conditional prediction even though its second replacement fails every singleton predictive fold. Requiring every singleton to pass would exclude this aggregate hypothesis before testing it. Here the aggregate passes through compensation between families, not evidence that both identities improve. The pair fails the original physical/ownership checks and worsens the exact full-scan RF objective. Joint conditional prediction alone is insufficient evidence for an association or localization gain.

## Frozen rule and scope

The reusable implementation is [joint.py](joint.py), frozen before new outcomes in [protocol.json](protocol.json). It reads the sealed RF influence ranking, takes the same top two families with summed local omission displacement at least 0.5 km, at least 30 fitted native points, and at least two tracks, and takes at most two whole-family nominees per target by summed full-family RF score. It forms their Cartesian pairs without requiring singleton predictive success. No identity is hard-coded in that rule. Stable fragment partitions remain excluded.

Pairs must have distinct destinations and, in this initial rule, cannot merge into an untouched existing family. The latter restriction is an algorithmic limitation, not evidence against physical identity. The original singleton discovery searched the full eligible causal bank using two longest tracks and equal per-arm budgets; this branch reuses its bounded nominees and does not claim a new exhaustive pair search. The pair penalty is the sum of the inherited nominee penalties plus `2 log(max(2, admissible pair count))`, applied independently in each c arm. For the only admissible pair this is 4.9698 objective units.

Exact replay uses the sealed population evaluator's ALGO06 reconstruction and build functions, including accepted native recovery and shared conditional attachments. Every input/code digest and original baseline replay is retained. This branch preserves original causal-history priors and their missing-history fallback; it does not add a history-completion intervention. Native likelihood observations and weights remain fixed. Candidate and incumbent controls receive the same published fitted-c and jointly omitted fitted-c position starts, 15 phase rounds, 40 SLSQP iterations, the original 25 km position box, original gates, exact orbit replay, 0.01 s phase-closure limit, optimizer check, and ownership checks. No continuation-only improvement is adopted.

## Why the sealed singleton shortlist stopped

| Case | Target → nominee | Sealed predictive result | Subsequent limitation |
|---|---|---|---|
| DS26-0203 | 67935 → 59360 | 0/5 wins in both arms; mean gains −17.4 / −13.5 | Destination already has published owners |
| DS26-0203 | 63377 → 68256 | 0/5; −1651.7 / −1670.2 | Destination already has published owners |
| DS26-0070 | 62320 → 63571 | 5/5; +2092.6 / +2100.4 | Singleton exact gates/closure/optimizer do not qualify |
| DS26-0070 | 62320 → 67047 | 5/5; +2075.1 / +2093.2 | Existing destination family; singleton exact checks fail |
| DS26-0070 | 63321 → 62422 | 0/5; −532.9 / −532.4 | Singleton predictive prefilter prevents exact fitting |

Numbers list c=0 / fitted-c. The original 0070 incumbent continuations pass residual gates but miss phase closure: approximately 0.447 s in c=0 and 0.043 s in fitted-c, versus 0.010 s. Thus the sealed absence of qualified controls is substantive and is preserved here.

## Direct pair prediction before singleton filtering

The only admissible frozen pair is **62320 → 63571 and 63321 → 62422** in DS26-0070. DS26-0203 has no admissible pair under the frozen ownership restriction; its sole Cartesian pair is explicitly retained in [pairs.json](DS26-0203/pairs.json) as an exclusion. The second 0070 pair is likewise excluded because 67047 already owns untouched evidence. No nominee expansion follows these outcomes.

The joint check removes both source families from RF calibration and position fitting. All target points remain in the predictive inventory. Five unique random synchronized 5-second held blocks use 5-second neighboring guards and the inherited seed 20261103, with at least five training and two held native points per graph source. Both families use the same partitions. Within each family, alias, shared phase, per-source offset, and shared rate are learned only from training data; family predictive scores are added over the same held groups. Priors/noise remain the inherited 300 Hz offsets, 0.5 Hz/s rate, 5 s phase, and 150 Hz noise, with phase grid −30 to +30 s in 0.4 s steps.

| Arm | Joint held gains, incumbent minus pair | Mean | Wins |
|---|---|---:|---:|
| c=0 | 261.2, 845.9, 685.0, 1598.0, 2172.8 | 1112.6 | 5/5 |
| fitted-c | 280.3, 866.5, 718.0, 1619.1, 2197.4 | 1136.3 | 5/5 |

This is **conditional predictive evidence**: catalogue nomination and graph construction previously used the full family data, and the folds overlap across repetitions. It is not independent catalogue discovery, a calibrated identity probability, or untouched-scan validation. Joint omission makes the calibration check appropriate for simultaneous replacement, while preserving both-family failures as possible outcomes. See [partitions](DS26-0070/partitions.json), [fold fits](DS26-0070/predictive_folds.json), [summary](DS26-0070/predictive_summary.json), and saved per-arm `.npz` physical predictions/residuals.

The decomposition matters: in this same joint cavity, 62320 → 63571 gains +1581.2 / +1597.7 on average and wins 5/5, whereas 63321 → 62422 loses −468.6 / −461.5 and wins 0/5. The earlier family compensates for poor late-family prediction in the aggregate score. The wrapped/lifted residual figure makes that late mismatch visible. This supports testing pairs before a singleton prefilter, while retaining the original per-track adequacy and exact acceptance requirements; it does not establish a physical interaction or two supported identities.

| Affected family, same joint cavity | c=0 mean gain | c=0 wins | Fitted-c mean gain | Fitted-c wins |
|---|---:|---:|---:|---:|
| 62320 → 63571 | +1581.2 | 5/5 | +1597.7 | 5/5 |
| 63321 → 62422 | −468.6 | 0/5 | −461.5 | 0/5 |
| Aggregate pair | +1112.6 | 5/5 | +1136.3 | 5/5 |

See the [per-family decomposition figure](figures/0070-predictive-decomposition.png) and [machine-readable gains](DS26-0070/predictive_per_family.json). The next general test should require positive predictive support for **each affected family under the joint-two-family cavity**, with matched groups and both c arms, before expensive exact refitting. That requirement concerns the joint cavity, where simultaneous calibration changes can matter, and must not be replaced by the old singleton-cavity pass. It is a proposed independently frozen next test; the present frozen result and its aggregate criterion remain unchanged.

## Exact refit and preserved interpolation failure

The first exact candidate attempt aborts before optimizer iteration 1: the inherited calibration orbit grid spans −17 to +317 seconds, while the frozen nominee phase for 62422 is +26.8 seconds. The joint marginal evaluates every native scan time and refuses extrapolation. All four abort receipts remain in the original pair's [fits.json](DS26-0070/62320_to_63571__63321_to_62422/fits.json). This is an implementation support limitation, not a physical rejection.

A separately frozen [supplement](supplement.py) extends causal orbit propagation to the existing predictive helper's −40 to +340 second integer grid, supporting the already declared ±30 second phase bound. It applies the same padding to candidates and controls, resets orbit caches, and verifies original objective differences of **exactly 0.0 in both arms and both cases**. This changes neither the physical prior nor a gate. Supplemental fits are labeled diagnostic and cannot alter the frozen result. No extra identity or position starts are introduced.

With adequate propagation support, the 63571+62422 pair completes all four exact fits but qualifies in none:

| Arm | RF objective | Published − trial, before 4.97 penalty | RMS (Hz) | Phase change (s) | Lost owners | Evaluation error (km) |
|---|---:|---:|---:|---:|---:|---:|
| c=0 | 22889.51 | −604.90 | 84.35 | 0.00111 | 30 | 18.277 |
| fitted-c | 22890.13 | −597.73 | 84.05 | 0.00599 | 30 | 15.043 |

Both starts agree closely. The optimizer fails, original profile/conditional step and slope gates fail, and exact orbit gate replay fails. The candidate reassigns 507 intended native owners and loses 30 other published owners, with no unintended reassignment outside the target families. Likelihood input IDs are unchanged; lost accepted owners are a separate output-gate failure. Neither the raw RF objective nor the penalized objective improves. Position errors are endpoint diagnostics and play no role in rejection. The alternative existing-67047 merge pair is also retained as a supplemental rejected diagnostic; see the full [fit table](fits.csv) for every start and arm.

## DS26-0203 existing-family merge audit

Both nominees already have published evidence. At the published fitted-c endpoint, 67935 has 129 native owners and phase −5.850 s, while 59360 has 231 and phase +2.128 s. Family 63377 has 108 and phase −0.678 s; 68256 has 140 and phase −4.857 s. Source/existing native-ID intersections are empty for both proposed merges.

There are 12 overlapping source/existing track intervals for the 59360 merge, up to 43.010 s, and six for the 68256 merge, up to 51.026 s. None has the same RX/channel pair: 67935 is on CH8 while 59360 has CH3/4/6, and 63377 has RX2 CH1/2/4 while 68256 has RX1 CH3/6. Such overlap is compatible with a single satellite across RF channels. Separate fitted baseline phases and individually adequate residuals do not establish separate physical identities. Per-track RMS, slope, lag, native IDs, phase, and overlap records are saved in [audit.json](DS26-0203/merge_audit/audit.json); the baseline native CFO/residual figure is linked below.

A valid merge inference must pool source and existing native evidence exactly once under **one shared phase, one shared orbit uncertainty prior, and consistent aliases/calibration for the merged identity**. It must preserve other incumbents and pass the same held-group and exact checks. Merely adding two separately fitted copies of the same NORAD would double-count prior/receiver information and would not test that model.

The supplemental merge reuses the frozen source aliases, maps both complete source families into their existing destinations, and shares each destination's existing phase/orbit prior. This initial pooled fit completes but fails all four cells: final phase changes are 18.81–18.90 s, optimizer/gates fail, and 377–435 published owners are lost. Its approximately 30.8 kHz conditional RMS flags severe incompatibility of this particular frozen-alias pooled construction. It is **not** evidence that every scientifically valid merge is impossible: aliases were nominated in singleton cavities, and no fresh jointly trained alias/phase discovery for existing-plus-source evidence was run. That remains the next bounded discriminating experiment if merge inference is pursued.

## Artifacts, figures, and limitations

- [Machine-readable fits, all arms/starts/failures](fits.csv), [original frozen protocol](protocol.json), and per-case results preserve the unchanged fallback.
- [Joint prediction, RF versus position effects, and original gate failures](figures/comparison.png).
- [0070 wrapped/lifted physical orbit overlays and conditional residuals](figures/0070-conditional-orbits-residuals.png), with [full-data conditional parameters](DS26-0070/conditional_full_parameters.json). These use the saved joint-cavity RF calibration and inherited phase/offset/rate model; the full-data curves are explanatory fits, not held-out predictions or the exact full-scan acceptance model. Native arrays are saved alongside the figure inputs. Solid red includes per-source offsets and the one shared rate per replacement identity; dashed blue is physical orbital CFO at the fitted shared phase. Alias wraps break lines, and the residual band shows the inherited 150 Hz noise assumption.
- [DS26-0203 published native context](figures/DS26-0203-context.png) and [detector fractional margins](figures/DS26-0203-scores.png).
- [DS26-0070 published native context](figures/DS26-0070-context.png) and [detector fractional margins](figures/DS26-0070-scores.png).
- [0203 existing-family native CFO and baseline residuals](figures/0203-merge-native-residuals.png).

Gray context points are other published owners, orange points are graph tracked but unassociated, black crosses are untracked, and red/blue highlight the two RF-triggered source families. Native detector scores are fractional margins, not probabilities. Target track spans are shaded; the native snapshot does not expose observation integration support in its observation schema. New polynomial-order or later-TLE searches were not run in this bounded pair branch; the original native graph/evidence and sealed causal screen remain the source. No new RF collection, reference-repository runtime dependency, production change, commit, or push occurs.

The scientific outcome is **unsupported for acceptance within this bounded paired shortlist**, with a demonstrated difference between singleton and aggregate prediction and an unexhausted existing-family merge alternative. Better aggregate conditional frequency prediction did not transfer to adequate exact full-scan fits or better localization. The original fallback is retained in both c arms.

Six component-owned tests pass, covering pair construction before singleton filtering, destination exclusions, random guarded groups, exact original/padded objective replay, fixed native fit IDs, no-adoption fallback, and disjoint merge observation IDs. The final artifact manifest records hashes and validates finite JSON numbers.

The lean publication file list is recorded separately in `publication_manifest.json`. Detailed per-point arrays, large exact-fit records, and the full causal ledger remain local, with their hashes and byte counts in `run_manifest.json`; publication need not duplicate them.

## Reproduction

Use `/srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python` with `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src:tools` from the recorded checkout. A fresh output copy is required: attempt/protocol receipts deliberately prevent silent repeated search budgets.

```text
python reports/2026_11_01_promotion_readiness/joint/joint.py freeze DS26-0203 DS26-0070
timeout 900s python reports/2026_11_01_promotion_readiness/joint/joint.py DS26-0203
timeout 900s python reports/2026_11_01_promotion_readiness/joint/joint.py DS26-0070
timeout 600s python reports/2026_11_01_promotion_readiness/joint/supplement.py DS26-0203
timeout 600s python reports/2026_11_01_promotion_readiness/joint/supplement.py DS26-0070
python reports/2026_11_01_promotion_readiness/joint/supplement.py audit DS26-0203
python reports/2026_11_01_promotion_readiness/joint/render.py
python -m unittest discover -s reports/2026_11_01_promotion_readiness/joint -p test_joint.py -v
```
