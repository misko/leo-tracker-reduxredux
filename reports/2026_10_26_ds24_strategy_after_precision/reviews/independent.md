# Independent review after the CFO and precision factorial

2026-10-26 UTC. This is a source and saved-result review. No new detector,
geometry, integration, position fit or launch approval was performed. New-scan
preparation remains held. Links below refer to the published report layout.

The strongest recent intervention worth replicating is complete-owner CFO
refinement. It is not yet a cohort-wide improvement or evidence that CFO error
is the principal physical limitation. The strongest quantified model degeneracy
remains position versus orbital timing/shape; its actual contribution to field
error is not identified independently of assignments and uncertainty calibration.

## What survives careful comparison

| Evidence | Supported conclusion and limit |
| --- | --- |
| Same 24 DS24 scans: all / low / high channels have fitted-c mean errors 1.220 / 1.558 / 2.040 km; c=0 gives 1.202 / 1.538 / 2.040 km | More of the existing channels help on average. All recordings are 10 MS/s, so this does not identify a sample-rate effect. |
| Thirty continuous restarts agree within 2.06 cm | Generic restarts have little justification for those fixed assignments. Discrete identity minima remain possible. |
| Conditional weak-direction scales 534 m, 110 m with timing known, 56 m with timing and shape known; median strongest timing/position correlation .935 | A substantial model degeneracy exists. These are conditional scales, not calibrated confidence, achieved accuracy or a physical error floor. |
| Smooth RX1 correction improves the development mean by about 100 m, but only 15.4 m on the later eight, with worse P95; the movement selector gains about 9 m with unchanged tails | The development-sized gain and favorable two-example selector did not transfer. Held-family scoring can still favor a harmful displacement. |
| Four complete owners, 159 refined measurements, two exposed scans | Raw nonlinear position errors improve 91–139 m across both c settings, but only one scan passes the frozen paired retention guard. This is a useful small intervention, not operational validation. |

Sources: [channel and information study](../../2026_10_24_ds24_bottlenecks/README.md),
[movement study](../../2026_10_25_ds24_movement_policy/README.md),
[later receiver validation](../../2026_10_25_ds24_phase_shape_validation/README.md),
and [complete-owner refinement](../../2026_10_26_ds24_complete_owner_refinement/README.md).
The larger retained ALGO01→ALGO02 result remains stronger cohort evidence:
404 common DS23 outputs improve fitted-c mean 1.870→1.508 km, while qualified
availability falls 407/413→404/413. Different cohorts and policies are not
additive benchmark stages.
[ALGO02 comparison](../../2026_10_19_algo02_ds23_full/README.md).

## What the factorial establishes, and what it does not

The 16-fit CFO × full-precision-packet experiment is a useful mechanism test.
Symmetric CFO/packet displacement norms are about 130/14–18 m in 0010 and
22/82–87 m in 0011. At the original packet, geographic CFO gains are
132.8/132.6 m in 0010 and 17.8/20.4 m in 0011, in c=0/fitted-c order. The old
local response predicts the isolated nonlinear CFO movement within 0.35–2.32 m;
its earlier large miss in 0011 should not be called a failed CFO derivative.

The packet contains **both fragment-noise and coefficient-prior precisions**,
including phase-prior precision. It was learned at a different VI endpoint from
the same exposed RF evidence. Thus “precision feedback matters” is supported;
“noise was wrong,” “the refined packet is physically correct,” and additive
percentages of geographic gain are not. The conditional Gaussian objective also
differs from the original VI objective, especially through 0010's predictive
factor. Fixed-state posterior closure does not require equal optimized endpoints.
[Factorial results](../../2026_10_26_ds24_cfo_precision_factorial/solver/FINDINGS.md).

Continuous fixed-cell GLRT64 refinement is established August prior work,
including exact/control refinement. The recent contribution is deployed-runtime
parity, complete preselected DS24 owners, and matched nonlinear propagation.
Inverse-template synthetic accuracy and increased field score do not establish
physical field CFO truth.
[Prior-art correction](../../2026_10_26_ds24_complete_owner_refinement/audit/PRIOR_ART_CORRECTION.md).

## Retention is an experimental guard, not physical truth

For 0011, all original position-likelihood IDs remain and single-arm fitted-data
and phase checks pass. The paired guard fails because **57 postfit-only IDs**
cross the slope limit in c=0: 2.999997410→3.007648003 and
2.906246753→3.056059076. Those are compatibility changes in unmodified owners,
not omitted fitted observations or proof of gross orbital mismatch.

Preserve the frozen failure and original-reference fallback. Report three
separate levels: detector/numerical measurement validity; actual position-
likelihood membership and fit checks; and postfit compatibility/paired retention.
Complete old accepted-ID retention is a conservative research guard. Its
necessity for this comparison does not establish that it is a physically
calibrated acceptance rule. Conversely, favorable GPS error and low target-fitted
RMS do not justify waiving it. A future rule change requires predeclared controls
and a separate comparison, not retrospective relabeling.
[Exact gate readback](../../2026_10_26_ds24_complete_owner_refinement/position/FINDINGS.md).

## Remaining identification and calibration gaps

- **Identity:** 0011's leading pair differs by only .384/1.289 in −2 log
  predictive density; 0012's leading pair reverses between saved parent states.
  Finite-pool ordering, a broad polynomial comparator, and repeated historical
  labels are not calibrated identity probabilities. Cavity removal changes
  conditioning; failure there cannot automatically be attributed to the untouched
  parent or to the proposed identity. The promising 0015 owner has no independently
  nominated same-label witness in the archived pool.
- **Phase/shape:** removing either generating component in eight shared synthetic
  realizations changes fitted-c mean error .4689→.4026/.4054 km; removing both
  gives .2966 km. The full three physical modes include constant/phase-like
  components. Generating B(phi) interaction and nonlinear error norms prevent
  interpreting this as an isolated inference defect or a real-data error floor.
- **Geometry and selection:** shared families, inherited graph/identity choices,
  learned noise and repeated scans limit independence. A nominal 40-degree feed
  separation is neither a measured bearing nor a spatial receiver baseline.
  More associated points or smaller conditional ellipses have already accompanied
  worse positions. Neither proves added physical information.

Sources: [identity challenge](../../2026_10_25_ds24_identity_components/identity/FINDINGS.md),
[phase/shape factorial](../../2026_10_25_ds24_phase_shape_validation/synthetic/FINDINGS.md),
and [0015 full-parent diagnostic](../../2026_10_26_ds24_cached_ambiguity/witness/FINDINGS.md).

## The next discriminating decisions

1. **Replicate the fixed measurement intervention on the already selected later
   four recordings.** First establish source/runtime/clock/causal-input and
   applicable site authority and reconstruct the exact retained baseline, not a
   seed-only substitute. Preserve both c arms, failures, coverage and fallback.
   Four cases can reveal transfer failure; they cannot validate tails or a new
   location. Stop a member at an authority or frozen-budget failure without
   replacement. No such launch is approved by this review.
2. **Split the two precision blocks before proposing a new weighting policy.**
   At one predeclared fixed CFO vector, the existing old/old and refined/refined
   packets supply the diagonal controls; the two missing mixed packets isolate
   noise versus nuisance-prior effects. The existing frozen-precision helper
   already supports this construction. The completed CFO × joint-packet test
   does not answer it. A saved-state normal-equation/gradient split is cheaper
   but cannot establish refitted endpoint mediation. Small prior-precision ratios
   do not prove a negligible effect along a weak direction. This would be a
   conditional mechanism diagnostic, not physical noise calibration. Independent
   frame/pilot prediction must then address temporal dependence and common bias;
   the August even/odd and older precision experiments must not be reinvented.
3. **Use genuinely separate observable support only when it exists.** Freeze a
   whole owner without selecting it for agreement, then predict it with shared
   radio/orbit covariance and no target-trained correction. Distinguish
   receiver-wide from family-wide behavior. If no independently nominated owner
   or useful new geometry exists, retain that absence rather than splitting an
   exposed owner and renaming it identity corroboration.

Stop repeating generic multistarts, favorable same-scan examples, smooth-path
variants, or increasingly exact integration without a changed scientific
decision. Numerical certification enables a comparison; it is not localization
improvement. The root strategy draft's policy distinction and replication-first
priority are consistent with these findings.
