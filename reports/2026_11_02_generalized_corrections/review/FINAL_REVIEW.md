# Independent final implementation and decision review

**The combined RF ledger passes the independent audit.** It contains exactly
205 available recordings, with no never-started recording left, no actual
attempt retried, and all worker pools joined. The paired policies accept A on
65 recordings and A+B on 73. C fully evaluates all 73 accepted B pairs and
abstains on every one. C is therefore a conservative abstention prototype with
no demonstrated ability to select useful B changes; its zero acceptance is not
evidence of successful localization risk control.

The authoritative combined result SHA-256 is
`1f09be8e05f716e53eadb6fda1a015dbeeb32b264e9b4588ffd62ccc97bc3347`.
[The complete audit](combined_audit.json) binds that exact result, the original
and coverage protocols, all frozen source hashes, every native input hash,
component and individual case receipts, and the authoritative per-case source.
It independently reconstructs the scientific decisions and exact A/B/C stage
fallbacks. No position fit, phase refresh or geographic evaluation was used by
the audit.

## Numerical and evidence contracts

A changes the numerical schedule while retaining the existing RF objective,
identities, native observations, noise policy and priors. Its position guard
compares the saved and candidate positions under one common final phase
reference. The archived-reference score difference remains diagnostic; changing
phase reference does not preserve one exact nonlinear marginal objective.
Endpoint qualification requires successful optimization, a stable central
gradient within 1e-4, raw unclipped phase closure within .01 s, finite inner
precision change <=1e-5, interior position, and the declared physical gates.

The audit verifies the full curved + conditional-entry + phase-mixture native
union and its immutable owners. Membership extensions are unadopted proposals,
not extra associations. Both c arms must qualify together. Unsupported baseline
evidence unions, preserved existing ALGO07 replacements, caps and partial stages
remain visible and retain their declared fallbacks.

[The paired-arm inventory check](paired_arm_inventory_check.json) additionally
verifies all 164 complete A/B model pairs have exactly equal native-ID and owner
hashes and equal initial phase references across c=0/fitted-c. All 73 C pairs
have equal eligible and other-family native-ID hashes across arms. Candidate
sets, causal covariance and maximum budgets are shared by construction.

B keeps the original three supported physical orbit directions, zero prior
mean and Gaussian normalization. Its matrix orientation is correct: transforming
columns by the Cholesky factor of the covariance produces `F C F.T`, while the
integrated coefficients retain a standard normal prior. The audit independently
verifies all 77 ready causal covariance receipts against actual TLE bytes,
satellite numbers, epochs, collection-time/source-hash witnesses, separated
history and the declared shrunk second moment. Historical phase alignments must
converge within their fixed bound. The nominal snapshot may have an earlier
verified duplicate collection of the same bytes; that is availability evidence,
not an independent epoch. These correlated TLE disagreements remain an
engineering covariance proxy, not calibrated orbit truth.

## What C measured

The guard excludes the target family and jointly projects other-family RF
against the union of both endpoints' hardware, band, drift, smooth calibration,
c, phase, orbit and fragment directions. Every family-deletion counterfactual
recalibrates its own retained rows. No fitted target hardware or saved phase
reference is frozen into the other evidence. C uses curved observations only;
ancillary pieces are counted and excluded. Its fixed150 noise and zero-reference
phase geometry are diagnostic approximations.

All 146 recorded guard arms fail the full displacement-information and RF-gain
thresholds of 4 and the family-deletion information threshold of 1. Another 112
have at least one opposing family-deletion RF contrast. There is no missing C
comparison among the 73 B-accepted pairs.

| Other-family diagnostic | c=0 | Fitted c |
|---|---:|---:|
| Median candidate displacement, km | 0.11954 | 0.11946 |
| Median unprojected displacement information | 184.45 | 210.66 |
| Median projected information | 1.21e-6 | 1.13e-6 |
| Maximum projected information | 0.000592 | 0.000488 |
| Median retained information fraction | 5.37e-9 | 5.38e-9 |
| Maximum projected RF gain | 0.04294 | 0.04248 |
| Nominal Gaussian gain positive at all three widths | 42/73 | 44/73 |

The unrestricted nuisance span removes almost all displacement information.
This can remove real position information that an externally justified orbit
prior would retain. In 42 pairs, the separate nominal Gaussian sensitivity
favors the candidate in both arms at all three declared SD multipliers (.5, 1,
2), despite projection abstention. Neither result proves correct localization:
the former shows weak separation under unrestricted nuisance, while the latter
depends on Gaussian engineering priors and reused RF. The thresholds have no
calibrated significance interpretation. Families also retain possible common
unmodeled orbit and hardware errors.

[The figure](../identifiability/guard_diagnostics.png),
[continuous arm diagnostics](../identifiability/guard_arm_diagnostics.csv),
[paired diagnostics](../identifiability/guard_pair_diagnostics.csv) and
[summary](../identifiability/guard_summary.json) retain these distinctions.
No Gaussian sensitivity was allowed to rescue a failed projection gate, and no
threshold was changed after cohort outcomes.

## Execution coverage and raw attempts

The original eight-worker window lasted 1,200.71 s and entered 124 recordings;
its terminal ledger retained all 205, including 81 queue placeholders. The
prospective operational coverage amendment was sealed before its new wave and
before candidate geography was opened. Its 16-worker wave entered only those
81 never-started recordings and finished in 667.05 s. The original eight actual
deadline partials, including two adopted A stages, were never retried or
replaced. The second allowed completion wave was unnecessary.

The combined recording statuses are 164 complete, 28 preparation/guard caps,
three preserved existing replacements, eight original deadline partials and two
unsupported baseline evidence unions. These recording statuses are distinct
from numerical arm-cell statuses. There are **341 terminal arm-cell receipts**:
334 complete and seven capped. One complete but unqualified B arm is an orphan
outside a completed pair and remains unadopted. Four further interrupted arms
have checkpoint-only evidence. Thus the observed attempted-arm lower bound is
345; interruption before the first durable per-arm marker prevents an exact
executed-cell count. All 304 qualified terminal endpoints remain visible.

The auditor independently checks each wave's source and protocol hashes,
nonoverlapping chronology, exact never-started eligibility and queue order,
per-case recording identity, and immutable provenance. Disjoint coverage waves
are an execution amendment, not independent statistical replications or new
scientific experiments.

## Bounded numerical replay

[The saved-endpoint replay](original_endpoint_replay_audit.json) evaluates three
deterministic original-wave recordings and eight A/B endpoints in 66.50 s,
without optimization or phase refresh. Every objective replays with exactly zero
difference; raw phase, central-gradient and native-ID checks agree. On both
DS24-0010 C arms, changing every target-track CFO by +1 MHz leaves every guard
output unchanged. An independent least-squares projection reproduces the guard's
SVD support calculation. The combined provenance audit verifies these exact
original rows survive unchanged in the final ledger, so no duplicate replay was
needed.

The component tests cover the solver, covariance normalization/provenance,
projection geometry, held-target perturbation, no-retry eligibility, immutable
stage merging and receipt tampering. These checks substantiate implementation
and honest abstention. Position accuracy is evaluated separately by the root
after the RF seal; this audit does not turn a better RF score into a localization
claim. No production model or persisted contract was changed.

## Separate postdecision reporting check

After the root released geographic reporting, the [table arithmetic check](position_table_check.json)
independently recomputed all 48 ALL/cohort × arm × policy rows from the 1,640
unique case/arm/policy CSV rows. Means, medians, percentiles, 500 m counts, >50 m
improvements/regressions, accepted-stage counts, selected-output counts and
association totals agree. C's reported position and output source equal A
exactly in both arms. This checks reporting arithmetic, not a second
geographic-truth calculation or an independently chosen selector. The root
README's numerical/guard thresholds and stage counts match the RF audit. The
reported small pooled mean gain, material B regressions and unchanged median
do not support promotion.
