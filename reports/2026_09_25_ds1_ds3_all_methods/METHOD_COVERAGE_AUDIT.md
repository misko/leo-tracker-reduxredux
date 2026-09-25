# DS1-to-DS3 method coverage audit

## Verdict

The present artifacts support the narrower statement **“all 31 numbered
iteration slots are represented in the accounting matrix”**.  They do not yet
support **“all DS1 methods were run on DS3.”**

The main reason is structural: the paired matrix has one row per integer
iteration, while several iterations contain multiple scientific method arms
and several methods in the frozen DS1 registries were never assigned their own
iteration.  The report builder repeats that assumption: it indexes post-seal
results by integer iteration, emits one report row per matrix row, and calls
the row count `methods`.

Evidence:

- `../2026_09_25_ds3_all_iterations_backfill/paired-completion-matrix-v3.json`
  contains exactly 31 rows, one for each integer 1 through 31.
- `run.py:364-383` indexes post-seal evaluation rows only by iteration.
- `run.py:397-467` emits exactly one comparison row per paired iteration.
- `run.py:483` reports `len(rows)` as the method count.
- `../2026_09_24_ds1_train_full/runner_registry.json` independently names
  eight executable method arms.
- `../2026_09_24_ds1_ds2_final_comparison/REPORT.md` independently freezes a
  17-model pre-DS2 inventory.

## Numbered-iteration audit

| Iteration(s) | Current inventory disposition | Audit finding | Required treatment |
| --- | --- | --- | --- |
| 1 | Missing historical artifact | The method identity is unrecoverable from the current registry. | Keep terminal as unknown/missing; do not imply that a scientific method was replayed. |
| 2 | One row for local refinement and timing | The historical run contains at least shared-global-time and regularized-per-scan-time arms. | Split into stable method IDs, even if both remain attached to iteration 2. |
| 3 | Mapped to `ds1_iteration3_diagnostics` | **Wrong historical binding.** Canonical iteration 3 is the prefix-6 joint global-tau plus causal per-NORAD-rate geographic screen in `ds1_joint_rate_search/ITERATION3_REPORT.md`; it produced positions and post-seal errors. | Rebind and run the canonical position method on DS3. Retain the diagnostics under a separate diagnostic ID. |
| 4 | Mapped to `ds1_iteration4_diagnostics` | **Wrong historical binding.** Canonical iteration 4 is seed-union exact selection in `ds1_joint_rate_search/ITERATION4_REPORT.md`. | Rebind and run the canonical position method; retain the diagnostics separately. |
| 5 | Missing historical artifact | **False missing classification.** Canonical iteration 5 is frozen-spatial common-grid timing refinement with `iteration5-results.json`. | Add the historical binding and DS3 adapter/result. |
| 6 | Mapped only to `ds1_iteration6b_session_scale` as legacy | **Conflation.** Canonical iteration 6 is the matched cap-300 proposal/cap-800 exact-rank ablation in `ITERATION6_REPORT.md`. Iteration 6B is a separate rejected legacy session-scale experiment. | Give canonical I6 and legacy I6B separate method IDs. Run I6; account I6B as rejected/not portable. |
| 7 | Missing historical artifact | **False missing classification.** Canonical iteration 7 is the fixed exact-residual Gaussian versus AR(1)+Student-t rerank in `ITERATION7_REPORT.md`. | Add both likelihood arms, or a parent method with two explicit arm IDs, and run/replay on DS3. |
| 8–11 | Bound to the canonical iterative reports | Correct numbered history. | Preserve exact parent and qualification propagation. |
| 12 | One row bound to session scale | **Collapsed family.** The authoritative comparison has rate-only expanded exact, regularized session scale, shared-NORAD control, and consistent cap-800 arms. | Emit separate method IDs. On DS3, evaluate shared-NORAD overlap before declaring equivalence; preserve timeout/not-run status for any arm not executed. |
| 13–14 | Canonical basin iterations | Correct numbered history. The separate `iteration13_stable_association` artifact is a prototype/diagnostic, not a replacement for I13. | Keep the prototype explicitly classified as superseded diagnostic. |
| 15 | Information-weighted result | Historically real, but its rate bounds were invalidated by iteration 19. | Keep the historical result and bind the I19 superseding audit; never rank it as qualified. |
| 16–21 | Canonical iterative/audit reports | Correct numbered history. | Preserve terminal qualification and ancestor status. |
| 22–25 | Marked terminal `no_position_diagnostic` | **Accounted but not run on DS3.** Each current DS3 JSON says `ds3_diagnostic_executed: false`. | Either execute DS3-native versions using fresh DS3 supports/folds, or state that these diagnostics were accounted for but not rerun. |
| 26 | `not_portable_legacy` | Correctly prohibited as the quartic rate surrogate; exact phase-atlas I27 supersedes its numerical premise. | Keep as superseded/not portable; do not manufacture a DS3 position. |
| 27–28 | Pending phase-atlas/basin chain | Portable and implemented by `batch-b/phase_atlas_chain.py`; execution remains pending. | Run after the sealed parent under the scheduler and preserve unqualified ancestors. |
| 29 | `not_run_adapter_unavailable` | **Stale classification.** The phase-atlas chain now implements I29. | Rebuild the completion matrix after a terminal I29 artifact; until then call it pending, not unavailable. |
| 30 | Fixed top-K soft preflight, unqualified | Correctly distinct preflight; it failed influence/temperature gates. | Keep terminal and unqualified. It is not the original soft-identity model. |
| 31 | Exact candidate-state soft preflight, unqualified | Correct successor to I30's missing-state test; it still failed influence stability. | Keep terminal and unqualified, with an explicit supersedes-I30 edge. It is not the original soft-identity model. |

Canonical I3–I7 evidence is summarized in
`../2026_09_24_ds1_iterative_subkm/REPORT.md:28-42`; the method-specific inputs,
outputs, and post-seal values are in
`../2026_09_24_ds1_joint_rate_search/ITERATION3_REPORT.md` through
`ITERATION7_REPORT.md`.

## Frozen DS1 model-registry coverage

The frozen 17-model registry is the strongest existing definition of “all
methods.”  Against that registry, the current 31-row matrix has the following
coverage:

| Frozen model | Current coverage | Finding |
| --- | --- | --- |
| Baseline Doppler | No explicit method row | Omitted. |
| Shared global receive time | Embedded in I2 | Present but collapsed. |
| Regularized per-scan time | Embedded in I2 | Present but collapsed. |
| Independent per-track time | No explicit row | Omitted; diagnostics exist in `ds1_timing_ablations`. |
| Causal per-NORAD orbit rate | No clean standalone row | Omitted/collapsed into later joint methods; `ds1_orbit_arm` is the standalone evidence. |
| Rate-aware joint geographic screen | Canonical I3 | Currently misbound to a diagnostic. |
| Soft identity mixture | No equivalent row | Omitted. I30/I31 are different successor preflights. |
| Equal-weight joint multiscan position | I8 | Represented. |
| Consistent cap-800 joint objective | I12 sibling / later basin work | Collapsed; the I12 attempt timed out and must retain that disposition unless rerun. |
| Shared-NORAD rate joint | I12 sibling | Collapsed; DS1 had zero overlap, and DS3 equivalence requires a DS3 overlap check. |
| Regularized common plus session scale | I12 | Represented as the authoritative I12 arm. |
| Learned pointing-cone quantiles | No numbered row | Omitted geometry diagnostic. |
| Fixed hard cone orientation | No numbered row | Omitted geometry diagnostic. |
| Staged full-FOV cone sweep | No numbered row | Omitted geometry diagnostic. |
| Local fitted full-FOV cone position | No numbered row | Omitted geometry position method. |
| Robust residual likelihood rerank | Canonical I7 | Currently falsely missing. |
| Legacy joint session-scale L-BFGS-B | I6B | Accounted as rejected/not portable, but currently masks canonical I6. |

The eight-arm executable registry adds two distinctions which also need stable
IDs: `global_time_plus_per_norad_orbit_rate` and
`soft_association_plus_global_time`.  Neither should be inferred merely from
the presence of a later numbered successor.

## Duplicates, supersession, and non-method reports

- `ds1_association_stability`, `ds1_grid_floor`, `ds1_iterative_subkm`,
  `ds1_subkm_ablations`, `ds1_ds2_final_comparison`, and
  `ds1_iteration_progress` are synthesis or diagnostic reports. Counting them
  again as inference methods would duplicate their underlying runs.
- `ds1_iteration2_ideas` is a design document, not an executed method.
- `ds1_iteration19_session_slope` has no scientific artifact beyond its
  placeholder and cannot be ported as a method.
- I15 remains historical evidence but is superseded for qualification by I19.
- I26 is superseded numerically by I27 and intentionally not portable.
- I30 and I31 are separate preflight experiments. I31 supersedes a defect in
  I30, but neither duplicates the original DS1 soft-association arms.

## Required fixes before using “all methods on DS3”

1. Keep the current integer matrix as an **iteration-completeness ledger**.
   Create a separate method registry keyed by stable `method_id` and optional
   `iteration`/`arm`; index post-seal evaluation by `method_id`, not only by
   integer iteration.
2. Correct I3–I7 historical bindings and add their DS3-native terminal
   results. This is the largest scientific coverage error.
3. Split I2 and I12 into explicit arms and restore the omitted baseline,
   independent-track timing, standalone orbit-rate, original soft-association,
   and soft-plus-time methods.
4. Add the four geometry/cone models from the frozen 17-model registry. Where
   DS3 lacks geometry-valid support, emit a terminal `not_applicable` result
   with measured support counts rather than silently omitting the method.
5. Execute I22–I25 DS3-native diagnostics, or change the publication claim to
   say they were accounted for but not rerun.
6. Rebuild I29's stale status after the implemented phase-atlas chain produces
   a sealed terminal artifact.
7. Record explicit `supersedes`, `superseded_by`, `qualification`, and
   `scientific_equivalence` fields so historical, diagnostic, rejected, and
   qualified results cannot be accidentally pooled.

Until these are complete, defensible publication wording is:

> All 31 numbered iteration slots are accounted for. DS3 reruns of the
> portable numbered position methods are in progress; distinct method arms,
> geometry models, and DS3-only diagnostics are reported separately.
