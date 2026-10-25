# Physical prior uncertainty and orbit-calibration qualification

Retaining a physical prior is different from certifying an orbit correction.
The current implementation uses `supported` for both numerical mode availability
and acceptance semantics. Expanding that one list therefore changes more than
the covariance. The lean initial comparison should preserve literal original
qualification, show its primitive residual/owner outcomes separately, and keep
the exact reference operational while evaluating diagnostic endpoints.

## What already exists

`tools/dsx01_all_candidate_uncertainty.py:expand_uncertainty` replaces
`p.supported` with all graph labels, rebuilds physical modes and records newly
included labels. The DSX01 follow-up already tested this idea; it is not a new
untested repair. With matched window noise, fitted-c S03 error improved
1.629→1.272 km but S01 worsened 0.512→0.619 km. The report explicitly notes that
expanded uncertainty activates the old two-owner gate and reduces accepted
coverage, while those observations remain in the inference likelihood.
[Published report](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_18_dsx01_radio_orbit_followup/README.md).

The prior new-family control used a different evidence role. The new whole
source was predictive-only; its phase and physical uncertainty were integrated
jointly with the existing predictive evidence, preserving shared calibration
covariance. It never entered curved calibration or learned target noise/Gamma.
On 0095, retained physical covariance prevented most of the zero-shape
regression but still lost to the reference. The experiment did not qualify the
target identity or an orbit correction.
[R2 report](https://github.com/misko/leo-tracker-reduxredux/blob/79f8bc300848c930e1a2879f8e268362cd97f232/reports/2026_10_25_ds24_new_family_uncertainty/README.md),
`scientific/adapter.py:joint_prediction`, `scientific/quadrature02.py` in the
archived R2 study. That target-only result does not establish the behavior of
expanding uncertainty in the existing parent likelihood.

## Exact current gate semantics

| Code | Existing meaning | Consequence of blindly expanding `supported` |
| --- | --- | --- |
| `tools/dsx01_joint_marginal.py:JointMarginal` | Allocates three shape columns only for labels with at least two distinct (receiver, channel) graph owners. | Shape columns and conditional-frequency predictions change. |
| `tools/audit_ds23_algo01_coverage.py:retained_metrics` | Requires profile RMS/bias, alias, visibility, noise and conditional-residual tests; then repeatedly rejects a passing row in `p.supported` with fewer than two remaining passing RX/channel owners. | Every newly included single-owner family can fail ownership mechanically, even with good primitive residuals. |
| `tools/probe_ds23_frequency_events.py:summary` | Predictive gates use the curved-posterior mean residual, original noise/profile/alias/visibility checks, and no predictive calibration feedback. | New parent shape posterior means also change predictive gate residuals unless explicitly separated. |
| `tools/run_ds23_combined_recovery_full.py:valid` | Both arms must pass the same curved/predictive gates, finite regional endpoint and phase-refresh checks; absolute unclipped phases must remain within the original bound. | A covariance score improvement never supersedes these predicates. |
| `tools/evaluate_ds23_phase_refreshed.py:extend_associations` | Uses accepted curved labels and receiver/band support, adding shape posterior corrections for `p.supported`. | Mode availability can inadvertently become new postfit association/calibration authority. |

Missing shape coordinates mean zero shape covariance in that model, not
independent evidence of an accurate orbit. Conversely, marginalizing a Gaussian
latent creates a conditional posterior mean mathematically. That mean is not
an independently validated physical calibration or satellite identity.

## Recommended bounded status policy

For this wave, freeze separate metadata sets:

1. The original calibration-supported family set and original graph-owner rule.
2. The expanded uncertainty-bearing set, with exact causal mode provenance.
3. Families whose added shape posterior is only an unqualified nuisance
   diagnostic; no new operational orbit correction is certified.

Retain the unchanged literal expanded-model gate results, including all
primitive residual checks and the owner cascade. Keep exact reference fallback
operational for the initial mechanism comparison. A mechanical owner failure
does not refute the physical uncertainty hypothesis; it does prevent claiming
the endpoint meets the existing operational qualification. No score or later
geographic improvement can convert it into an accepted output.

If an original-ownership-semantics gate view is separately examined, declare it
before execution. Merely hiding newly included families from `supported` while
still subtracting their fitted shape means would silently remove an acceptance
guard. A conservative view must exclude the new unqualified shape means from
curved conditional residuals, orbit-profile predictions, predictive residuals
and postfit extension, retain the original calibrated-family owner cascade and
every threshold, and save the literal results alongside it. This would be an
explicit diagnostic adapter, not an unchanged legacy algorithm or a license
to adopt it. It need not delay the first fixed-state mechanism test.

Kernel audits should check that old semantic columns/priors, full native IDs,
aliases, masks, powers and c pairing are unchanged; added mode covariance is
positive semidefinite and physically scaled; old/new predictive covariance is
joint; dormant priors are not duplicated; and original residual/ELBO
normalization is preserved. The conditional shape means, covariance contribution
and calibration/qualification flags must remain distinct in saved records.

No fits or new geographic outcomes were read for this review. The four cases
are development-exposed. The next decision should depend on a material fixed-RF
effect and an audited bounded experiment, with no operational promotion inferred
from these four scans alone.
