# Rebuild calibration across acquisition settings

Use the qualified availability-correct N23 geometry, not the older N24 fit.
Export all 23 contributing DS10 recordings, with family/role fixed by the
metadata-only acquisition inventory's chronological halves. Every capture and
finalization precedes the earliest target. Preserve exact sample rate and RF
families, original visit masks, training-only 0.90 candidate confidence threshold,
and all full-scan paired observing opportunities. Source labels remain inferred,
not verified identities. The shared geometry uses training data from both donor
roles, so receiver transfer validation remains conditional on that geometry.

Reconstruct the original per-object causal catalogue and verify selected states
against the original banks before computing LOS with the new geometry/timing.
Verify public track point time, CFO, RF, receiver and visit identity. Unknown
candidate ownership must be marginalized/marked unknown, not labeled absence.
A definite source hit in a window overrides another ambiguous hit for that
source: bit aggregation must be order-independent. Empty observed opportunities
are retained for later activity/detection modeling; no claim of verified physical
absence or calibrated clutter follows from these exports.

One child per donor, capped at 90 seconds, at most three single-thread children.
No new RF, DS11 reference-error fitting, old coefficient reuse with new geometry,
or published contract changes. Keep every failed export receipt. Six families
have disjoint donor records for calibration/validation; two 2.5MS/s families
currently lack a validation donor under the conservative global cutoff. The
full DS11 goal remains intact; those gaps require further support rather than
being silently removed from the objective.
