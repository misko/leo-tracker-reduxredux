# Independent scientific critique and next decisions

The strongest supported bottleneck is weak separation of receiver position
from satellite timing/shape under the current Doppler model. Identity,
construction and measurement errors remain possible. Neither a physical noise
floor nor a single dominant implementation fault has been demonstrated.

| Claim | What the evidence actually establishes |
| --- | --- |
| Orbit/position ambiguity | The [fixed-identity information controls](https://github.com/misko/leo-tracker-reduxredux/blob/2fe12901af295dec83ad6b5b9b278da9526ab6c3/reports/2026_10_24_ds24_bottlenecks/information/REPORT.md) give median weak-direction scale 534 m, versus 110 m with phase known and 56 m with phase and shape known; median strongest phase correlation is 0.935. These are conditional oracle sensitivities, not achieved errors or permission to tighten priors. |
| Continuous local minima | Thirty restarts agree within 2.06 cm for tested retained models. Generic additional starts are low priority; discrete identity/ownership alternatives were not exhausted. |
| Sample rate | The usable fast-scan comparisons all use 10 MS/s. No matched rate contrast identifies sample rate as the cause. |
| RX geometry | Nominal feed angle affects visibility, not measured bearing. Bands share a median 11 calibration families, with weak axes separated by 17.7 degrees. More channels can repeatedly constrain the same uncertain orbit. |
| Association reliability | Smooth membership, postfit compatibility, likelihood membership and true identity differ. Related pipelines can share catalogue/model errors; agreement is not independent identity truth. |
| Residual precision | The rejected full DS23 recovery and RX2 remeasurement demonstrate that more associations or smaller CFO scatter need not improve position. The later RX1 test transfers only 2.744/15.444 m mean gain with worse P95 in both arms. |

The [blanket active-parent uncertainty test](https://github.com/misko/leo-tracker-reduxredux/blob/2fe12901af295dec83ad6b5b9b278da9526ab6c3/reports/2026_10_25_ds24_parent_orbit_uncertainty/evaluation/FINDINGS.md)
qualified none of four research pairs despite completing 16 fits. The
[phase-dependent physical-mode control](https://github.com/misko/leo-tracker-reduxredux/blob/2fe12901af295dec83ad6b5b9b278da9526ab6c3/reports/2026_10_25_ds24_ch5_prediction/parent_coupling/summary.json)
has largest local movement proxy 0.571 m. These are reasons to stop repeating
those specific broad covariance/local coupling variants. They do not prove
all physical uncertainty is harmless. Full three-mode blocks include level
and phase-like components; conclusions about isolated curvature would be
stronger than the interventions performed.

The present wave adds two useful results, neither a position improvement.
The [14 real screens](portions_terminal.json) nominate 57450 for every prefix
and 65871 for every suffix; whole W still nominates 57450. All six portions
fail the original duration-and-curvature conjunction. Rank one is only a
proposal: whole-W affine phase and unadjusted residuals differ greatly from
the short-prefix prediction. Dormant `p.supported` mode slots are not active
parent evidence, independent owners or corroboration.

The [matched-law control](matched_law_terminal.json) now closes the earlier
full-parent-versus-response-cavity mismatch for its **exogenous c0 target
law**. All four generating physical labels rank first in ordinary c0
nomination, so this panel supplies no reason to widen the shortlist.
Two physical finite-pool orders resolve correctly; two have overlapping
conservative numerical intervals. Nonseparation of bounds is not proof that
the exact distributions are intrinsically indistinguishable. Both deliberately
near-null draws have physical finite-model winners, with c0 minimum ordering
margins 0.698/0.357 log units. This is possible for overlapping proper
distributions even when the generating/scoring law matches. There was no
operational acceptance rule; two designed draws cannot estimate field false
acceptance or calibrate class priors. Fitted-c scores the same c0-generated
vectors off-law and is not another matched-law calibration experiment.

This control is not IQ-to-position closure. The layouts were inherited from
response-selected real owners; calibration/noise is exogenous and fixed;
even catalogue labels active in the old parent receive fresh independent
target priors. It does not reproduce shared-family hierarchical conditioning,
winner-selected peak errors, graph crossings or source discovery. No new
position estimator or receiver-model correction follows directly from it.

The three most discriminating next directions are:

1. **Close the specific whole-versus-two-source physical explanation once.**
   Test whole 65871 alongside whole 57450, the predeclared 57450-prefix /
   65871-remainder hypotheses and proper unresolved controls on all original
   D+W observations. Preserve shared radio covariance, owner constants,
   satellite-specific phase/modes and normalized allocation/alias priors.
   A separately nominated complete owner can then test a held prediction;
   old CH3 nomination is exposed and cannot be multiplied in as independent
   significance. Stop if complete-source alternatives or interval bounds
   remain unresolved within a small fixed budget. A split preference alone
   does not prove a crossing: the [native trace](https://github.com/misko/leo-tracker-reduxredux/blob/2fe12901af295dec83ad6b5b9b278da9526ab6c3/reports/2026_10_25_ds24_source_coherence/ownership/FINDINGS.md)
   established no second CH4 continuation near 250 s. No gate waiver or
   favorable-prefix acceptance follows.

2. **Test a decision policy for whole-source ambiguity, rather than search
   harder for labels already nominated.** Compare conservative deferral with
   carrying a few complete causal assignment hypotheses plus a declared
   unresolved alternative. This differs from the old active-family-only
   soft-label control, but its class priors and unknown model are assumptions,
   not calibrated identity probabilities. Begin with RF-selected cases and
   fixed-position/weak-axis diagnostics; freeze the fallback, covariance,
   hypotheses and numerical policy before any bounded matched-arm position
   experiment. Stop if the predicted movement is immaterial or the ordinary
   source/parent requirements fail. Geography must not select labels, portions
   or prior odds. Only if curve-level closure leaves a concrete detector
   discrepancy should a tiny clean/weak/crossing injection replay test native
   winner selection. That requires accessible archived IQ/noise windows and
   a bounded runnable original detector; those prerequisites are not yet
   established by the export inventory. Do not repeat another easy inherited-
   label simulation or an extreme-null precision campaign.

3. **Allocate recovery to independent position information, with a feasibility
   stop.** The [common-pool ranking](https://github.com/misko/leo-tracker-reduxredux/blob/2fe12901af295dec83ad6b5b9b278da9526ab6c3/reports/2026_10_25_ds24_nomination_information/information/FINDINGS.md)
   predicts only about 5–21 m weak-direction SD reductions on 0010–0012;
   the 127 m result uses already-exposed, unqualified 60108. Compare at most
   one information-selected complete owner against one length-selected owner
   from the same eligible pool/budget, after identity competition. More owners
   of one satellite can test consistency while retaining shared orbit error;
   a different satellite direction can add geometry. Stop if no unexhausted,
   adequately supported informative source exists. The [metadata review](../METADATA_FINDINGS.md)
   supports only two exported schemas/current authorities, not absence of
   useful information everywhere. An additional observable needs verified
   transmit-time, power/pattern, pose or synchronization calibration first;
   missing companions are a stop result, not a fabricated bearing or range.

The main generalization gap is exposure. Current DS24 examples are development
data; resplitting inspected scans is not fresh validation. Same-site/radio
success does not establish new-location transfer, and the earlier 24-to-eight
receiver test already shows why a development mean gain is insufficient.
Any release needs one frozen policy, matched c arms, complete failure/fallback
denominators, likelihood versus postfit counts, and paired mean and adverse
tails on an exposure-checked unused block. Broad DS23 evaluation should follow
a credible small-study mechanism rather than substitute for one.

The root [review](../REVIEW.md) is consistent with these distinctions. This
critique uses saved evidence only and introduces no new inference campaign.
