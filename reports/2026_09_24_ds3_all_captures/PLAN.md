# DS3 all-capture positioning model plan

DS3 is the fresh 56-capture freeze through 22:20:02.797011Z on September 24.
DS2 is the prior published 22-capture snapshot identified as `d27cd889`; its
existing artifacts remain under `ds2_sep24_rerun_22`. DS2 results are historical
comparators and are not DS3 results.

`model-inventory.json` selects exactly ten scientifically distinct and runnable
families. It records their executable entry points, input contracts, nuisance
parameters, association behavior, reference isolation, observed runtime scale,
and DS3 readiness. `evaluation-matrix.json` fixes the fair comparison scopes and
qualification gates and gives DS1 qualified evidence, DS2-22 results, and the
pending DS3-56 cells side by side.

The admission manifest contains 56 qualified raw captures, including all 22 DS2
members and 34 new captures. Tracking and causal cache products are now sealed
for all 56. Every ordinary model consumes all captures passing the common
positioning eligibility rule; none falls back to the 22 previously analyzed
sessions.

The six general families are ordinary Doppler, shared global time, regularized
per-scan time, joint causal per-NORAD rate, soft identity, and consistent
cap-800. The capped objective may run only after the fresh DS3 joint-rate parent
seals. Independent per-track timing and robust residual reranking are retained
only in excluded diagnostic history because prior runs showed no positioning
benefit.

The remaining four families are the exact arms in `geometry-cone-plan.json`:
geometry-only, fixed-up cone, learned zenith-cone, and global-time plus cone.
DS2 conservatively admitted three geometry bindings. The stricter DS3 live
capture-time audit verified embedded LT3D bindings for `294be` and `ff02a`, so
DS3 has five eligible geometry sessions and excludes the other 51. Their fair
controls must be recomputed on those same five sessions. Geometry5 results
cannot enter the all-eligible-DS3 rank.

The derived DS3 positioning manifest and whole-session cohorts are frozen. All
ten entries executed without a reference coordinate and passed their declared
structural gates before post-seal evaluation. DS3's best all56 result is the
4.030559 km consistent-cap point; the ordinary, timing, causal-rate, and soft
parents share a 4.231110 km basin. The 3.039075 km consistent-cap point belongs
to DS2-22.

The DS3 source of truth is:

- `reports/2026_09_24_ds3_all_captures/manifest.json`
- `reports/2026_09_24_ds3_all_captures/manifest.sha256`

Historical comparisons are drawn from:

- `reports/2026_09_24_ds1/REPORT.md`
- `reports/2026_09_24_ds1_ds2_final_comparison/REPORT.md`
- `reports/2026_09_24_ds2_portable_evaluation/REPORT.md`
- `reports/2026_09_24_ds2_consistent_rate_screen/REPORT.md`
- `reports/2026_09_24_ds2_missing_models/REPORT.md`
- `reports/2026_09_24_ds2_geometry_cone_evaluation/REPORT.md`
- `reports/2026_09_24_ds2_sep24_rerun_22/REPORT.md`
