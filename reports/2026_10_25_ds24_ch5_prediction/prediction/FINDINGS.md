# CH5-only prediction: CH3 inconsistent, CH4 budget-limited

The complete 57-point RX2 CH5/T001 source, conditional on hypothesis 57450,
does **not** corroborate the complete 24-point CH3/T002 source as the same
family. Both c arms favor an unresolved CH3 witness while keeping CH5 physical.
The CH4/T000 comparison (43 points) is **budget-limited and unqualified** in
both arms. Its primary checkpoints are not promoted into terminal decisions.
No position fit, geographic truth, identity acceptance or operational ownership
change was used or produced.

The comparison is shared-57450 **D+W** versus physical-57450 **D plus a proper
polynomial W**. D is physical under both models. Their D denominator is common,
so the conditional odds are bounded directly from joint evidences. The two
witness folds reuse D and must not be summed as independent significance.

| Witness | c arm | Terminal status | log Z(shared) − log Z(D physical/W polynomial), certified bounds | Raw same-minus-mixed −2 log evidence |
| --- | --- | --- | --- | ---: |
| CH3, 24 IDs | c0 | unresolved W favored | [−1194.004, −839.082] | +2378.207 |
| CH3, 24 IDs | fitted c | unresolved W favored | [−1192.940, −838.052] | +2376.070 |
| CH4, 43 IDs | c0 | budget-limited / unqualified | not reported | not promoted |
| CH4, 43 IDs | fitted c | budget-limited / unqualified | not reported | not promoted |

These are conditional model-consistency results. They do not rank alternative
CH3/CH4 identities, authenticate 57450, prove that every point belongs to one
source, or establish an absolute acceptance rate. All completed model scores
remain unqualified at the stronger 1e-3 absolute-precision criterion; CH3's
separate disjoint-bound ordering still passes.

![Conditional comparison; CH4 open points are nonterminal checkpoints](conditional_evidence03.png)

## CH5-only conditional diagnostics

The D marginal reproduces the previous CH5/57450 objective **exactly** in both
arms: 677.6552494183604 and 675.6922024452792. D values, parent coefficients and
Gamma precisions are exact; the joint-background D covariance differs only by
at most 2.91e-11 Hz² from the prior independently constructed marginal.

The following estimates condition on D alone. No W CFO value enters their
posterior weights, predictive means or moment bands. Fixed GL32/64 integration
passes every predeclared objective/phase/alias/latent/prediction stability check.
This is quadrature stability, **not** a certified posterior-moment error or
calibrated uncertainty coverage.

| D-only quantity | c0 | fitted c |
| --- | ---: | ---: |
| Phase mean, s | 0.711916 | 0.718675 |
| Phase model SD, s | 0.036753 | 0.036760 |
| Shape coefficient means, unit Gaussian-prior coordinates | [−0.838, −0.026, +0.017] | [−0.702, −0.023, +0.015] |
| D source-constant mean ± model SD, Hz | 464.07 ± 168.81 | 283.99 ± 173.25 |
| D alias-zero posterior mass, original track gauge | approximately 1 | approximately 1 |

The original causal Student location/SD are −1.766182/6.391009 s before
conditioning on [-15,+15] s. The physical modes are reevaluated at each phase.
Their posterior means are conditional latent pulls, not independently learned
or validated orbit corrections. In particular, shape modes 2/3 retain variances
near one (about 0.9997): their small means do **not** mean those modes have been
calibrated. Phase, modes, source constant and radio uncertainty trade off;
these posterior summaries are not a causal component-ablation experiment.

![D-only phase, alias and nuisance diagnostics](report02/D_posterior.png)

## Predictive curves without refitting W

Both W sources are predicted from the same D-only phase/mode/radio posterior.
Each W retains its independent original 300 Hz constant and native noise.
The blue band integrates D's phase/alias posterior and shared physical/radio
uncertainty **conditional on the displayed fixed W alias**, including W's
constant/noise. It is moment mean ±2 SD, not a calibrated 95% interval or the
variance of the full nine-image raw-W alias mixture. Alias zero below is a
**fixed inherited graph gauge**, not selected to fit W.
The observations retain their original uniform −2 PERIOD offset from the native
measured-CFO ledger; this is not a native absolute-alias assignment.

![Fixed alias-zero CFO observations and D-only predictions](fixed_alias0_CFO03.png)

![Fixed alias-zero predictive residuals in Hz](fixed_alias0_residual03.png)

For this fixed image, CH3 differs over its main body rather than only at the
isolated final point. CH4 visually departs after roughly 250 s. The latter is a
saved-array diagnostic; its timed-out model comparison stays unqualified.
Neither pattern licenses trimming, a new cutoff, relabeling or a favorable
source selection. [All nine alias images](report02/witness_predictions.png)
remain plotted, and [all 134 matched-arm witness rows](fixed_alias0_residuals03.csv)
are saved with predictions and residuals. None is refitted to W.

## Matched law, limits and runtime

All models use the exact previous **CH5 discovery top-eight union cavity**, its
saved parent phase references and one common c0 RF coordinate. The cavity is
not chosen from W's nominations. Parent radio/noise/calibration is frozen;
shared radio D–W covariance, one shared family phase/three physical modes and
independent owner constants are retained. The mixed model adds polynomial
covariance on W only; its D and cross-radio blocks are unchanged. Both arms
retain every original native ID, original priors/powers/noise and uniform nine
aliases per owner (81 joint, nine D). Original accepted ownership remains
unchanged and there are no accepted 57450 parent owners.

Nominal visibility support is D∩W for shared-family and D only for mixed.
Original conditioned-Student normalization is retained, with invisible
likelihood zero and no visible-mass renormalization. Existing support/log-domain
integration/physical bounds are reused without extending tolerances or caps.
This remains a conditional development-source approximation, not a full
catalogue challenge, generative calibration experiment, independent validation
or detection-selection model.

Four arm/witness slots were declared. CH3 completed both models and references
in both arms. CH4 completed the mixed models and the same-family primary
integrals/support bounds; both arms then reached the original deadline during
the same-family independent GL reference. Those two primary checkpoints remain
explicitly nonterminal. There are six terminal joint-model records, two partial
joint-model records and two completed D replays, with all failures preserved.

The first frozen attempt failed in output-path handling before any evidence
integral, spending 7.320185383781791 worker seconds. The root's explicit
[narrow harness-repair authorization](../HARNESS_REPAIR_AUTHORIZATION.md)
permits only Path-to-string normalization plus its port test. Original source,
protocol, four failure records and RF seal remain unchanged. A generated pytest
cache touched by the new test was restored to its exact original sealed bytes;
the changed cache and initial audit failure are also preserved.

Revision02 used separate [run02 outputs](run02/), deducted that exact time and
kept every scientific input, threshold, ordering rule and model unchanged.
The total was **599.9836192852817 scientific worker seconds**, including the
first failure, under the 600 s cap. There was no scientific retry, extension,
point deletion, new RF, position fit, GPS read or automatic factor adoption.
Eight owned tests and the independent terminal artifact audit pass. The failed
first attempt remains in the execution history, not hidden from the denominator.

The old “2442 Hz under 57450” attribution is not used here. The
[historical provenance correction](../audit/ARCHIVAL_CORRECTION.md) establishes
that salvage could relabel a row while preserving earlier cached residuals.
Current full-57-point D evidence and these predictions are newly computed under
the explicitly stated model, independent of that stale label/residual pairing.

## Next decision and replay

This wave supplies a real conditional falsification for CH3 and a visible,
unqualified CH4 prediction diagnostic. It does not provide the missing
independent same-family corroboration needed to turn CH5's finite-pool
preference into a trusted association or position factor. CH4's time-local
departure can motivate a separately bounded source-coherence investigation on
the existing observations; it does not justify retaining only its favorable
prefix. No position gain is established, and none is assumed from frequency
evidence or posterior concentration.

[Protocol](run02/protocol.json), [source](prediction02.py),
[owned tests](test_prediction02.py), [RF seal](run02/RF_seal.json),
[four-slot summary](report02/summary.json), [table](report02/conditional_table.csv),
[report seal](report02/report_seal.json) and [readability/overlay seal](plot03_seal.json)
retain the complete source-bound result. Reproduction uses one BLAS/OMP/MKL
thread and the existing repository plus /tmp/algo03-feasible-deps Python path.
The runner refuses existing outputs. Do not rerun this completed output tree.
