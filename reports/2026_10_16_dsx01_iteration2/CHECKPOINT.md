# Iteration 2 checkpoint: progress, with the recovery goal still active

The previous goal turn made progress by measuring the 15 windows and fitted
timing distributions. This turn changes authoritative state: it implements and
tests an exact all-point timing search, executes matched-budget and c=0
comparisons, restores candidates through a generic causal-catalogue screen,
and identifies a concrete error in the temporal calibration protocol.

## Current measured results

These are full-data development association counts, not satellite-identity
accuracy. The descriptive major-window threshold is at least 80% net recovery
of that window's originally missing associations, with all 15 windows retained.

| Method | Window associations / 693 | Major windows / 15 | Whole-scan associations / 20,084 |
|---|---:|---:|---:|
| Original | 96 | 0 | 11,222 |
| Earlier A, 180 calls | 253 | 4 | 11,880 |
| Earlier A, matched 1,000 calls | 249 | 3 | 12,006 |
| Continuation, 1,000 calls | 95 | 0 | 11,226 |
| Exact profile, fixed bank | 422 | 6 | 13,784 |
| Exact profile, expanded bank | 434 | 7 | 14,248 |

![Same 15 windows, including expansion regressions](iteration-expanded-windows.png)

The matched A control shows that raising the evaluation allowance alone does
not reproduce the new profile gains. The fixed-bank method strongly restores
001, 005, 007, 008, 009 and 015. The expanded method strongly restores 005,
007, 008, 009, 013, 014 and 015. These are different sets: expansion reduces
001 from 79/86 to 45/86. Do not combine per-window maxima from those methods
and report them as one algorithm.

The full table, paired RMS, timing/position plots, matched c=0 sensitivity and
separate expanded-continuation control are in [README.md](README.md), with
raw memberships and counts in [window-comparison.csv](window-comparison.csv).
All 90 matrix receipts are checked in [validation.json](validation.json).
All 33 component tests pass, including candidate transport, full-point timing
evidence, held-CFO isolation, band-freeze closure and bounded numerical cleanup.

## Root causes actually established

1. **The old proposal gates discard useful evidence.** The selected 48 arcs
   cover only 274/693 requested observations; the full existing arc pools
   cover 646. Window 008 contributes no selected arc, and a passing 17/22-point
   arc for 013 becomes failing 11/16 after subsampling. The complete diagnosis
   is in [arc_diagnostics.md](arc_diagnostics.md).
2. **Candidate pruning blocks some exact hypotheses.** 69433 and 57864 are in
   their original causal regional catalogues but absent from the selected S01
   and S05 banks. The generic screen restores 57864 without an ID override.
   It does not select 69433: that candidate ranks 129th at the saved S01
   geography/calibration. This is evidence that retention alone does not fix
   the early S01 case. No oracle candidate was inserted.
3. **The old temporal test omits calibration learning.** It fixes both band
   contrasts to zero permanently, whereas production learns approximately
   -15 kHz / +40 kHz. The missing columns are independent of the other retained
   calibration columns in every fold. Its low held coverage is a restricted
   zero-contrast stress result, not a matched end-to-end generalization result.
   See [cold_protocol_audit.md](cold_protocol_audit.md).

## Numerical convergence is separate from recovery

The primary fixed-bank profile has four strict initial endpoints. A uniform
cleanup policy applies only to failed audits with unspent original allowances;
it changes neither the model nor its physical bounds. S01 requires four extra
evaluations: total 870/1000, KKT 0.0040554 → 0.0007309, identical memberships.
Thus all five fixed-bank profile recordings have a strictly audited numerical
endpoint available after cleanup. Their geographic and identity correctness
is still unverified. Original receipts remain immutable, and the parent report
retains its unpolished counts and audits explicitly.

Uniform cleanup receipts are in `polished-results/`; remaining failures and the
exhausted S01 c=0 allowance are retained. Some tiny residual stationarity failures
do not resolve under this bounded cleanup. No threshold was relaxed.

## Work remaining and next experiments

The goal is **not complete**. The fixed profile loses 742 original full-scan
assignments while adding 3,304; the expanded profile loses 791 while adding
3,817. Counts and frequency improvements do not prove those replacements are
correct. Some position-reference distances remain over 100 km. Window 003
remains entirely unassociated, and several other windows remain mostly lost.

The training-only band bootstrap is implemented and has four component tests.
Its actual S03 smoke restores the missing two calibration directions and passes
strict optimization, with exact freeze closure below 1.2e-10, but reaches a
poor neutral-histogram local solution. Learned offsets are about +28.9/-79.0
kHz and held coverage is 11.74%. This is a negative initializer result, not a
successful correction of the predictive validation. See
[cold_band_smoke_S03.json](cold_band_smoke_S03.json).

Next actions, in priority order:

1. Improve the training-only calibration initialization. Test a causal prior
   from earlier, same-hardware fast recordings for stable band contrasts,
   while estimating the current recording's offsets/drifts on training data.
   Find and bind actual earlier receipts before using them; do not use the
   target recording's full-data calibration. A small portfolio of training-only
   histogram modes is another controlled initializer arm. Compare full learned
   band-calibration pipelines on both temporal directions with matched budgets
   and c arms. Do not rerun the known restricted-zero-contrast protocol as if
   it validated the production model.
2. Audit the support replaced by the new exact profiles and retain competing
   timing/identity modes through excluded-trajectory scoring. Do not simply
   lock all original identities, since they are not truth labels. Any retention
   constraint must be a separately declared arm with the same original metrics.
3. Test stronger relative timing priors (2, 1, 0.5 s) jointly with geometry
   initialization and a matched continuation. Large timing shifts can absorb
   wrong geography; a smaller in-sample residual or a tighter timing histogram
   does not establish localization. Keep c=0 sensitivity controlled and report
   frequency/position separately.
4. Revisit causal element age and available Space-Track alternatives as a
   separate provider/epoch arm. Current restoration deliberately retains each
   original TLE snapshot, so it cannot establish that the original snapshot
   was the best available element-age choice. Keep observations and budgets
   fixed within each provider comparison.

No new recording, hardware command, production change, fixture update, or
remote push was performed. Unrelated tracked work remains unchanged. The
scientific runtime is the same pinned `/opt/leo-fast-auto/f141dbb.../worker/src`
with the existing `/opt/leo-tracker/releases/47e2705.../.venv/bin/python`.
Full executable paths remain in the parent [runtime instructions](../2026_10_16_dsx01_models/RUNTIME.md).
