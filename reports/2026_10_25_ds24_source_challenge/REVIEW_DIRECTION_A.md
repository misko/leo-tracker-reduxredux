# Independent direction review A

Reviewed the preceding [cumulative assessment](../2026_10_25_ds24_source_coherence/REVIEW.md),
the current [portion results](portions/FINDINGS.md), and the saved component
controls. No new inference was run. My priority is a decision that can affect
the position estimator; another explanation of one rejected curve is useful
only with a clear endpoint.

**The strongest measured gains remain the early estimator changes.** ALGO01
to ALGO02 lowers mean error on404 common DS23 outputs by350/362m for
c=0/fitted c, with qualification falling407/413→404/413. Equal-prior family
comparison adds a separate modest30/29m mean benefit on410 scans. These gains
cannot be added across different comparison populations. The smooth RX1
correction's90/100m development gain becomes only about2.7/15.4m on eight later
scans, with worse P95 in both arms. There is no newer comparable transferable
position gain.

The strongest mechanism evidence favors orbit/position ambiguity, not simply
too few starts or noisy CFO. The DS24 conditional weak-direction scale changes
534→110m when timing is known, versus534→386m when receiver terms are known;
the median strongest timing/weak-position correlation is0.935. These are
conditional model sensitivities, not achievable errors or an irreducible floor.
In the eight common known-label synthetic realizations, removing generating
phase+shape deviations changes mean artificial error0.4600/0.4689→0.2954/0.2966km;
removing receiver deviations does not help the mean. The completed factorial
finds comparable phase and shape effects, not phase-only dominance. None of
this authorizes narrowing priors or treating a posterior orbital correction
as independently measured truth.
[Component control](../2026_10_25_ds24_identity_components/synthetic/FINDINGS.md),
[factorial](../2026_10_25_ds24_phase_shape_validation/synthetic/FINDINGS.md).

## What has been tested enough to stop repeating

* Thirty targeted continuous restarts finish within2.06cm; channel-half label
  transfers yield no qualified better full-data result. This deprioritizes
  generic multistart, without proving global identity optimality.
* Full DS23 recovery raises association70.08%→75.08% but worsens fitted-c
  mean1.469→1.591km and P953.157→3.473km. More membership is not the objective.
* Remeasuring322 RX2 curves reduces median scatter78.07→22.18Hz without a
  qualified cohort position gain. RX1's largest later regression improves
  RMS5.917Hz while worsening position261m. Generic denoising/reweighting is
  not a sufficiently specific next hypothesis.
* Retaining missing active-parent physical covariance produces material RF
  movements but all four tested cases fall back under original conservative
  residual/coverage policy, despite phase/Gamma convergence. Separately, the
  phase-dependent active-parent shape control has at most0.571m local effect.
  These do not justify another unsupported-owner gate waiver or broad orbit
  flexibility campaign. [Parent control](../2026_10_25_ds24_parent_orbit_uncertainty/scientific/FINDINGS.md).

The previous review also records tried soft-label, temporal/HMM, correlated
prior, sample-clock, log-volume and receiver variants. A revisit needs a new
falsifiable mechanism, not a renamed selector or another fit-quality target.

## Is the CH4 lead becoming too narrow?

It is a real lead: the normalized partial-physical class has full-domain
log-evidence margins2.969/3.277 over its declared alternatives, and unforced
catalogue screens now nominate57450 on every prefix and65871 on every suffix.
The whole source still nominates57450 first. That last control prevents
mistaking the rank pattern for a demonstrated switch.

Its likely cohort position benefit is currently weakly supported. It concerns
one43-ID owner that was already structure-flagged and rejected. The favored
8.858/14.524s prefixes cannot enter old curved salvage; even the20.195s prefix
fails curvature. Recovering another channel of the same57450 family mostly
repeats shared orbital uncertainty already present in the CH5 discovery. No
new independent projected geometry or accepted likelihood factor has been
established. Overlapping portions and the two c arms are not independent
replications. A split preference against one broad polynomial prior is also
not a complete competing-satellite test.

One bounded closure is justified. An open-ended CH4 numerical/segmentation
project is not. Any later whole-CH3 check must retain all24 IDs, including its
isolated endpoint, and condition shared latent uncertainty correctly; its old
65871 nomination is exposed evidence, not a fresh confirmation.

## Three next experiments, ranked

1. **Test a whole-source deferral or multiple-hypothesis policy at fixed RF
   positions.** The completed [matched-law branch](matched_law/FINDINGS.md)
   puts all four generating physical labels first in the ordinary c0 screen.
   Exact finite-pool orders favor both0010 generating identities; both0011
   physical draws retain overlapping numerical intervals. Both deliberately
   close null draws favor a physical model, with conservative c0 log-evidence
   margins0.698/0.357. These are model rankings, not operational false positives
   or a population error rate. Interval overlap does not itself establish an
   intrinsic tie. Fitted c is an off-law sensitivity on the same observations,
   not a second matched-law sample. There is no demonstrated shortlist failure
   to repair by widening this panel's nominations, and no reason to reroll it.
   The useful next prototype compares conservative deferral with a few complete
   causal-family assignments plus unresolved status on a small RF-selected
   ambiguous panel. This must extend beyond the already-tested active-family
   soft labels: include absent families, whole-owner exclusivity, shared
   radio/orbit uncertainty and a proper unknown model. Check its effect along
   the RF weak-position direction before any GPS evaluation or position fits.
   Freeze one cap and policy; stop if its RF effect is immaterial or qualification
   cannot preserve original ownership. A generating label need not win every
   noisy draw. Full acquisition/graph selection remains a separate gap.

2. **Measure cohort applicability and available new information before another
   position campaign.** Start with a metadata-only ledger of eligible unused
   complete owners in the frozen24 usable scans. Exclude already exhausted
   nominations from the claim of new recovery. If a genuinely untested pool
   exists, freeze at most four cases by capture metadata, not GPS/error, and
   run a bounded fixed-position qualification/information pilot with complete
   native-ID ownership and ordinary alternatives plus unresolved outcomes.
   Retain radio/orbit uncertainty and distinguish identity corroboration from
   new weak-direction position information. A predeclared RF-only materiality
   rule, for example≥5% weak-variance reduction in both arms, can decide whether
   a later position trial is worth doing; it cannot accept an identity. Stop
   before fits if no qualified new source exists or the predicted effect is
   immaterial. Do not repeat the prior four-candidate ranking and call the
   already unqualified0013/60108 hypothesis a new discovery. Positive results
   would justify a separately frozen predictive-only transfer policy with exact
   baseline fallback, preserved accepted IDs, and exposure-checked evaluation.

3. **Close57450/65871 once as a conditional source test.** Keep all100 CH5+CH4
   IDs and compare whole57450, whole65871, the normalized split model and
   proper unresolved controls. Account for both physical phases where needed,
   shared radio covariance, full physical-mode priors, aliases and the
   cut/allocation prior. Suffix runner-up65876 is a useful explicit competitor;
   otherwise state that the test remains conditional on65871, not validated
   identity. Freeze one compute cap and numerical ordering rule before scoring.
   If whole65871 explains W, investigate whole-source identity. If a split is
   distinguishable and predicts a separately owned complete source, that
   supports a source model, not calibration admission. If bounds overlap,
   adequacy fails or the cap is reached, retain unresolved status and end this
   case. No more precision engineering or prefix promotion. Cohort work still
   requires experiment2's applicability/information bridge.

Root's final REVIEW now places stage diagnosis ahead of source closure and
requires a cohort bridge before a splitting/recovery policy; I agree.
The scalar metrics and source caveats otherwise agree with the saved evidence.
Its instruction to test whole65871 is essential. The metadata inventory also
correctly stops at missing calibration authority: detector epochs/scores and
nominal feed angle do not supply ready range or bearing. A targeted companion
lookup may later be justified, but it is not yet an alternative position factor.

Any promotion must finally demonstrate paired position benefit, tail behavior,
qualification and coverage preservation under matched c arms. Better source
scores alone are not that demonstration. All current DS24 examples remain
development evidence; repartitioning them does not create an unseen test.
