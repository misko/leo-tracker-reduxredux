# Receipt-only timing saturation: DS21-009, DS21-011 and original DS21-039

Timing saturation varies by starting proposal in DS21-009 and is absent from
all 36 audited DS21-011 endpoints and the three original DS21-039 controls.
Their total-timing and geographic constraints are interior. Active saturation
is not shared by every observed combination failure. This does not exclude
effects from interior timing or calibration/association coupling. The selected
DS21-009 B/all and B/high
fits reach the lower timing bound for **different catalogue candidates**.

The [compact receipt audit](TIMING_SATURATION_009_011_039.json) covers exactly
the predeclared **75 endpoints**: all six starts for B/C × all/low/high in
DS21-009 and DS21-011, plus the original training-selected DS21-039 C
all/low/high endpoints. All
75 retain their original stationary certificates. There were **zero new fits,
likelihood evaluations, orbit evaluations or reference calculations**. Training
winners are marked using the unchanged own-objective selection rule; accuracy
did not select endpoints or change the audit scope.

| Case | Model/view | Start / original proposal | Training winner | Binding candidate | Bound |
| --- | --- | --- | --- | ---: | --- |
| 009 | B/all | 4 / shape-high | Yes | 66266 | −20 s |
| 009 | B/low | 3 / shape-low | No | 66266 | −20 s |
| 009 | B/high | 1 / cold-1 | Yes | 56805 | −20 s |
| 009 | C/all | 2 / cold-2 | No | 59548 | +20 s |
| 009 | C/low | 2 / cold-2 | No | 69347 | −20 s |
| 009 | C/high | 4 / shape-high | No | 66266 | −20 s |
| 009 | C/high | 5 / shape-all | No | 66266 | −20 s |

These are the only seven boundary endpoints. No candidate and bound side are
active across all six starts of any view. Within a matched DS21-009 B proposal,
`shape-high` is saturated in all but inside the timing/geographic constraints
in both halves; `cold-1` is saturated in high but inside those constraints in
all and low. Thus the selected all/high flags
do not represent one shared binding candidate or a constraint reached by every
start. Candidate66266 recurs in several views and models, but its posterior
support was not persisted in the DS21-009/011 fit receipts. The audit cannot identify
an emitter, establish strong support for that candidate or assign causal
importance to its timing constraint.

All DS21-011 B/C endpoints have interior total-timing and geographic constraints;
their recorded minimum feasibility slacks
range from 0.230269 to 5.171763. The original DS21-039 C all/low/high controls
also have interior timing/geographic constraints, with minimum slacks
3.883087 / 2.925079 / 2.903380. The published
[009 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_009_RESULTS.md)
shows B combining worsens while C combining improves, and the
[011 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_011_RESULTS.md)
shows combining improves both B and C. Original DS21-039 C combining worsens despite
inactive timing/geographic constraints. Saturation is a feature of particular
DS21-009 solutions; the audit does not isolate the effects of interior timing.

For every endpoint, total candidate timing is reconstructed as
`v[7] + Helmert(K) @ v[8:]`, preserving original candidate-number ordering.
The JSON retains every total shift, signed lower/upper slack and change from
its original seed, plus common timing, saved calibration terms/frames,
objective, likelihood NLL, their difference, original stationarity fields and
regional/local disk slacks. It also reports candidate-and-side frequencies
over all starts, 48 matched-proposal all-versus-half comparisons and six B/C
active-set comparisons. Raw receiver intercepts from differently centered
frames are not compared.

The original core flags a boundary at minimum timing/geographic slack
**<1e-6**, uses active KKT normals at **≤1e-6**, and admits physical slack
**≥−1e-7**. These rules remain distinct; common timing and coefficient bounds
are not included in the stored boundary flag. Original mixed units are retained:
timing slack is seconds, disk slack is squared kilometres. A reconstructed
−3.553e-15-second slack is retained without clipping and is within the original
feasibility allowance. No KKT or likelihood certificate was recomputed.

All recorded constraint minima replay within **1.421e-14**, below the fixed
1e-8 gate. Original DS21-039 timing also matches its saved calibration arrays within
**5.329e-15 s**, below the fixed 1e-9 gate. The DS21-009/011 bounds verify saved
training extrema and bound bank-node intervals. Historical DS21-039 extrema were not
persisted; its archived core requires
`coverage_min < max(-20, coverage_min)` and
`min(20, coverage_max) < coverage_max`, which force exactly ±20 seconds for
every admitted fit. This source invariant avoids new observation preparation;
missing historical extrema are not claimed to have been independently replayed.

The audit checks 2,726 distinct file hashes, including live/archive source
closures of 411 numerical and 412 reader files per new case and 319 original DS21-039
diagnostic files. The JSON binds the case/parent/init/call/review receipts and
the actual archived Helmert, constraint and fitter sources. Both independent
[009](../2026_10_13_ds21_release_readiness/THREE_MODEL_009_AUDIT.json) and
[011](../2026_10_13_ds21_release_readiness/THREE_MODEL_011_AUDIT.json) receipt
audits passed before this arithmetic audit began.
The subsequent independent reconstruction of all 75 rows, source bindings and
comparison tables passed.

The existing DS21-039 [association results](RESULTS.md) and
[calibration results](../2026_10_13_ds21_039_root_cause/CALIBRATION_RESULTS.md)
already show calibration/geography-timing interactions and changed
associations despite inactive constraints. Those stored controls remain
evidence of coupling, not proof of wrong identities or hardware calibration.
Shared discovery and physical initialization, plus C's inherited all-training
receiver lifts, limit half-view independence. This audit introduces no new
nuisance terms, timing limits, priors or per-case reference tuning.
