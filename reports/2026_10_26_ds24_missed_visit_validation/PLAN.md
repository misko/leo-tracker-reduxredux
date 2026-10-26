# Second and final bounded prototype: curvature-aware timing prediction

This round follows the sealed missed-visit timing-search study at `../ds24-missed-visit-r01`. It keeps the active goal: determine whether trustworthy new CH5–8 observations reduce position error, or identify the obstacle with discriminating evidence. No new RF, QNAP mutations, production-contract changes, geographic tuning, or noncausal TLEs.

## Frozen direction before new outcomes

Use the primary causal branch from round1. Implement the exact conservative timing quadratic proposed in `../ds24-missed-visit-r01/prediction/ROUND2_PROPOSAL.md`: at least five distinct donors over at least one second; centered/scaled rank-three least-squares design with condition number at most100; absolute timing acceleration at most10samples/s²; propagated absolute timing rate at most200samples/s. Otherwise retain the original linear/fallback prediction and disclose its status. Do not fit a target-dependent constant timing bias. Do not use the unresolved empirical RF-coupling sign as a physical law.

Keep the earlier CFO prediction and its reference conventions unchanged. Compare one earlier-only primary linear timing prediction with one earlier-only primary quadratic/fallback prediction, both scored on the same full20ms target. Each method has one timing proposal, with no target timing search or target-based mode selection. Preserve no-donor cases. Compare existing round1 search outcomes separately; their random-frame split and computation differ.

All timing/CFO reference conversions must be explicit. The scorer's constant epoch should be evaluated at the midpoint of its target interval; the quadratic model itself remains evaluable at any native counter. Its covariance and added model-discrepancy scale are engineering uncertainty, not measured likelihood weights.

## Stages and decision rules

1. Prediction owner implements/tests the causal quadratic in `prediction/`, freezes source and all development forecasts before target scoring. Start with exactly the round1 metadata panel and same primary branch; no new target-based nomination. Do not open held-validation target outcomes yet.
2. Timing owner proposes a compact known-signal/null protocol and lean raw replay in `timing/`. Controls must test frequency innovation beyond an already-accurate prior, both edges/signs, nonzero timing/CFO evolution, and timing errors between coarse-grid points. Full-window pilot support and actual frequency information are separate. No outcome before root binds the final source/control protocol.
3. The first raw stage reuses the exact288development paired windows. Native public index/IQ identity and full reader exhaustion remain mandatory. The historical runtime and all previously verified paired detector parity may be reused instead of repeating blind acquisition at the same windows; disclose that distinction. Never modify round1 artifacts.
4. After the method is sealed, use the same metadata-only four-fraction/channel panel on the twelve held-validation recordings. These recordings were seen by older studies; they are held out only from developing this revision. Do not adjust the method after opening them.
5. A bounded coherent expansion or position comparison is a dependent application of this sealed method, not a third tuning round. Root must specify targets, budgets, source ownership and comparison arms before running it. Nomination may use RF evidence but never geographic error. Add new native owners only; do not automatically replace valid baseline measurements. Existing graph, active-curvature and full-catalogue causal association gates stay unchanged.

Matched c=0/fitted-c comparisons, the25×25km regional box centered at37.906,-122.545, and GPS-for-final-evaluation-only remain required. A better frequency fit or more pilot detections is not evidence of lower position error. The working promotion screen remains at least10% lower validation median without worse p90 in each c arm; no500m or new-location claim without corresponding measurements.

Each numeric process is bounded to at most600seconds with BLAS1; at most six numeric workers total and two per timing branch. Report completed, failed and capped attempts. No multi-hour campaign or automatic sweeps. Source/policy/diagnostic changes must be separated from scientific outcomes. Publish this iteration and its limitations to remote main, alongside the immutable first-round report.
