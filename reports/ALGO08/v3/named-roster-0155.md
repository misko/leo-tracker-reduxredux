# Where named v3 builds the DS30-0155 roster

The original named route reproduced all **3,498 ordered owners per calibration arm**, including the signed alias and likelihood rows. The largest disjoint CPU charges were **4.503 s** for initial ranking, **4.059 s** for input preparation and **3.692 s** for held-family nomination. The whole conservative salvage call charged **1.394 s**. No isolated exact reuse or compiled replacement examined here had a credible three-second saving. This investigation measured the original route and made no scientific changes. [Frozen protocol](named-roster-0155-protocol.md) · [Receipts and source profile](measurements/named-roster-0155.json.gz)

## Disjoint process CPU

| Original installed operation | Calls | CPU s |
|---|---:|---:|
| Prepare tracks, causal sky, noise and history | 1 | 4.059 |
| Convert prepared values | 1 | 0.064 |
| Construct scan contexts | 2 | 0.173 |
| Rank original discovery assignments | 1 | 4.503 |
| Fit the screened initial winner | 1 | 0.743 |
| Conservative paired gates and recovery | 1 | 3.923 |
| Family/history policy and predictive fit | 1 | 3.324 |
| Signed history context | 1 | 0.072 |
| Held-family nomination | 1 | 3.692 |
| Other work between preparation and selected evidence | — | 0.105 |
| **Preparation entry to selected-evidence call** | | **20.659** |

The conservative charge contains **2.394 s** in two executed `fit_and_gate` calls, **1.394 s** in salvage, **0.096 s** in association extension and **0.040 s** in the caller. The two gates invoked six actual arm fits. Salvage includes one separate zero-calibration unit-prior fit (**0.189 s**), 35 coarse profiles (**0.054 s**) and 12 fine calls (**0.982 s**). The conservative paired fit uses causal phase widths. Reusing its result as the unit-prior salvage seed would change that fit. Stable recovery already handles the case with exactly unchanged roster and mask. [Conservative policy](../../../src/leo/analysis/localization_v3/conservative_recovery.py) · [Retained fits](../../../src/leo/analysis/localization_v3/retained_position.py) · [Installed stable reuse](../single-core-2x/solver-recovery-reuse.md)

The history charge includes **0.662 s** for the curved policy refits and **1.359 s** for the two original `linear_refit` calls. The other **1.302 s** covers family weighting, history validation and predictive-entry preparation. The wall profile assigns **1.061 s** within that remainder to `confidence_for`. The predictive fitter was observed as stock. The signed context ran without a signed refit. Held-family nomination found no positive offer, so the downstream cavity fit was never called. [History policy](../../../src/leo/analysis/localization_v3/history_policy.py) · [Inference and offer gate](../../../tools/pipeline_eval/variants/v5_core.py)

## What an exact replacement could remove

The following subcall times are inclusive wall measurements from the same worker. They explain the CPU stages above, so adding them to those stages would double count work.

| Possible target | Paid scope | Exactness and budget |
|---|---:|---|
| Initial discovery projected geometry and statistics | 0.982 s in `evaluate` under `fresh_discovery` and `explore`. 1.142 s in `statistics` and `augment_phase_statistics`. | The two measured scopes total 2.124 s. The named release already removes repeated identical associations and gathers only changing projection rows. Its four centre proposals, two refreshes per centre and four corners feed the exact ranking. The earlier interpolated moment shortcut changed the winner on DS30-0008. |
| Conservative fine support pruning | 0.982 CPU s | The earlier certified bound and length dominance are exact. Even free fine scoring and its remaining checks cannot save a second here. The named path already defers a noise screen when an original cheap gate fails. |
| Held-family work | 1.576 s in broad projection, 1.241 s in leave-family-out calibration and 0.718 s in 144 candidate predictions | The broad and calibration pieces together charge 2.817 s. The original shortlist and score still require the held-family samples and independent nuisance posteriors. The shared-timestamp projection already runs. Omitting nomination merely because this control ended without an offer would remove the check that established that outcome. |
| Preparation | 1.645 s for causal sky, 1.410 s for tracks and 0.640 s for phase history | The three costs cover distinct inputs to the original solve. The graph and causal parser optimizations were already enabled. A three-second saving would require replacing most of all three operations. |
| Likelihood calls across stages | 3.235 s in `NativeBound.__call__`, including 1.664 s at the native call and 1.085 s in the dense hierarchical routine | This sum spans several stages and includes the unchanged handoff. Saving three seconds there would remove over 92% of the entire measured likelihood port. Prior exact full-input memoization showed little portable whole-solve gain. |

[Original discovery](../../../src/leo/analysis/localization_v3/discovery.py) · [Exact discovery workspace trial](../single-core-2x/solver-discovery.md) · [Time-moment counterexample](../single-core-2x/solver-track-moments.md) · [Certified salvage](certified-salvage.md) · [Held-family scoring](../../../src/leo/analysis/localization_v3/family_cavity.py) · [Existing shared projection](../single-core-2x/solver-cavity-projection.md) · [Complete likelihood reuse](../single-core-2x/solver-exact-likelihood-reuse.md)

## Science and run boundaries

| Calibration | Horizontal error from the archived score | RF RMS Hz | Ordered owners |
|---|---:|---:|---:|
| `c = 0` | 0.972 km | 155.420160 | 3,498 |
| Fitted `c` | 1.157 km | 155.382354 | 3,498 |

The corrected worker passed the archived checks for both positions and full ordered ownership, including original roles, aliases, the fixed likelihood and nuisance design hashes, and objective replay. The archived unprofiled selection took **19.315 CPU s** from the saved wrapper to selected evidence, then **0.248 s** for owner/objective reconstruction without grid. The equivalent profiled intervals were **21.191** and **0.330 CPU s**. The **20.659 s** breakdown starts later, at the preparation entry, and includes profiling overhead. The successful child exited in **22.476 elapsed / 22.468 CPU s** with no filesystem input blocks. The first child reached selected evidence and passed the owner and endpoint checks but failed to save profiling data when the old comparison helper required a second route. Its separate exit clock was **23.569 elapsed / 23.563 CPU s**. Five focused tests passed, including receipt persistence across a failed independent comparison. No candidate replay was run. [Earlier complete publication](prospective-0155-solver.md) · [Archived selected-roster comparison](cross-roster-0155.md)

The successful control ran the committed driver at `c8f0385fd` against the existing signed request in `/dev/shm/leo-v3-saved-0155-pair-01`. Run `named_roster_0155.py launch NEW_TMPFS_ROOT` with the pinned installed interpreter and payload on the import path, under the shared low-priority CPU 2 Gauss lock with one numerical thread. The staged offer and 52 causal snapshots remain unchanged. The diagnostic uses the saved acquisition handoff and stops before the grid and figures. [Driver](named_roster_0155.py) · [Tests](../../../tests/pipeline_eval/test_named_roster_0155.py)
