# A small receiver-contrast correction for an embedded positioning pipeline

This is a design proposal, not an accuracy result or deployment change. It
responds to the preference for simple, effective mathematics even when a more
expensive algorithm could achieve slightly better accuracy. The frozen
iteration87 residual audit must first establish whether paired receiver bias
remains under B7. No additional fits or reserve outcomes are consumed here.

## Recommendation: estimate a small correction from pairs, then freeze it

If the audit supports a satellite-dependent receiver difference after accounting
for receiver-common time/channel effects, the smallest useful experiment is a
small weighted least-squares estimate of zero-sum satellite contrasts. Freeze
those contrasts and perform one ordinary same-start positioning refit. Do not
immediately add another block of variables to every iteration of the full
nonlinear optimizer. Simple paired-mean shrinkage is a special case, justified
only when the common-effect audit supports it.

This proposal retains the reference-free structure of the
[receiver-contrast hypothesis](../2026_10_09_position_error_iter86/NEXT_MODELS.md).
The indices represent inferred candidates for the current recording, not stored
hardware corrections for particular satellite IDs or geographic locations.
All observations remain in the positioning likelihood. An unsupported contrast
is zero; insufficient paired support makes the extension a no-op.

## What a receiver pair measures

For genuinely simultaneous observations of the same transmitted component, write
`y_r = g_r(position, satellite, time) + receiver_correction_r + error_r`.
The receiver difference cancels the common transmitted carrier and, for colocated
receivers using a common geometric prediction, the geometric Doppler term.
Subtract the existing model's receiver correction before estimating an additional
contrast. If receiver-specific antenna locations are modeled, retain their
predicted differential Doppler rather than assuming it is zero.

Cancellation depends on conditions that the join alone cannot prove:

- Rounded-millisecond timestamps are not necessarily identical physical sample
  times; a time mismatch leaves a Doppler-rate times timing-error term.
- The two observations must refer to the same satellite and the same spectral
  component. A common satellite/channel label is necessary, not sufficient.
- RF-center differences or inconsistent modulo-frequency unwrapping can produce
  artificial differences. Respect the existing circular residual convention and
  audit values near its branch boundary.
- Remaining common receiver clock, RF-stretch or time-varying calibration error
  can look satellite-dependent when satellites are sampled at different times
  or frequencies. Paired means do not establish an LNB or satellite fault.

The existing audit conditions on ordinary fitted-B7 assignments, averages duplicate
observations within receiver/satellite/channel/rounded time, and then differences
the receivers. It is therefore a conditional diagnostic. No reference coordinate
is needed, but association and previously fitted nuisance parameters can still
carry model error into the proposed correction.

## First distinguish common receiver error from satellite interaction

The historical means around−25 to−32Hz could all represent one remaining common
receiver offset. They do not by themselves establish different satellite errors.
Even a zero-sum constraint cannot remove time confounding when different satellites
are observed during different parts of a drifting receiver clock. Channel coverage
can produce the same ambiguity.

Before fitting a satellite correction, measure between-satellite paired residual
variation after removing a globally specified receiver-common intercept, a small
time basis, and identifiable channel effects. Use paired observation times and
channels, not just one mean per satellite. The existing iteration87 aggregate
pair summaries establish prevalence but omit raw pair times; a separately frozen
diagnostic can reconstruct those pairs from the immutable endpoints if warranted.
Do not claim that those summaries alone distinguish a satellite interaction.

A small proposed linear model is
`q_i = a(t_i) + channel_effect_i + satellite_contrast_i + noise_i`.
An intercept plus centered linear time term is an initial small clock basis;
its adequacy must be diagnosed, not assumed. Channel effects need a zero-sum
constraint or one omitted level. Remove dependent columns deterministically and
report rank deficiency; a satellite observed only in one channel/time pattern
may not be distinguishable from those nuisance effects.

For a background design X, zero-sum satellite design Z, pair precision W and
Gaussian contrast precision lambda, solve the small regularized least-squares
problem `min ||sqrt(W)*(q-X*beta-Z*theta)||² + lambda*||theta||²`.
Let Q span the background columns of `sqrt(W)*X`, and define
`P = I-Q*Q.T`. Then

```
theta = solve(Zw.T * P * Zw + lambda*I, Zw.T * P * qw)
Zw = sqrt(W) * Z
qw = sqrt(W) * q
```

Implement projection through the small Q factor; never allocate the pair-count
square matrix P. This estimates contrasts from what remains after the specified
common receiver effects. Zero-sum remains useful but is not a replacement for
this projection or a rank/coverage audit. Background coefficients are diagnostic
here: freezing only the contrast avoids introducing an untested extra receiver
clock-update policy into the position refit. Account explicitly for the possibility
that a richer clock basis is needed instead of any satellite correction.

With K eligible satellites and L background columns, a dense small normal system
costs approximately O(Pairs*(K+L)²+(K+L)³); sparse group sufficient statistics or
block elimination reduce that work. It is a single linear solve per recording,
not another nonlinear variable block evaluated on every candidate iteration.
Use stable QR/rank-aware factorization where possible rather than explicitly
forming a matrix inverse. Identifiable background removal can change the
contrasts substantially; its result must be tested, not treated as equivalent
to unadjusted paired means.

## Closed-form zero-sum shrinkage when common effects are controlled

Let `q_kj` be the RX1-minus-RX0 residual difference for paired observation j of
eligible satellite k. Let `w_kj >= 0` be frozen measurement precisions. Define

```
W_k = sum_j w_kj
b_k = sum_j w_kj * q_kj
lambda = 1 / sigma_d**2
a_k = W_k + lambda
```

Estimate the full receiver difference d by minimizing

```
0.5 * sum_kj w_kj * (q_kj - d_k)**2
    + 0.5 * lambda * sum_k d_k**2
subject to sum_k d_k = 0.
```

Only one scalar Lagrange multiplier is required:

```
eta = sum_k (b_k / a_k) / sum_k (1 / a_k)
d_k = (b_k - eta) / a_k
```

This simpler special case is an O(P+K) reduction for P pairs and K eligible satellites, with O(K)
sufficient-statistic storage after joining. It needs no matrix inversion,
eigendecomposition, or nonlinear optimization. Sorted pairs can be processed
with a merge; unsorted data require a hash join or sorting. The prior width sigma_d
and weights must use consistent Hz units: if weights are unit counts, lambda
must include the assumed pair-noise variance rather than blindly using
`1/sigma_d**2`.

The zero-sum constraint removes the mode already represented by a receiver-wide
clock difference. It is not a guarantee of observational identifiability. Unequal
time/frequency coverage can still mix contrast with other receiver corrections.
Apply the same fixed paired-support eligibility rule as the proposed joint model:
at least10 pairs per eligible satellite and at least2 eligible satellites overall.
Keep corrections zero for ineligible satellites. Zero prior variance must be
implemented as an exact zero correction, not division by zero.

Do not deploy this simpler formula merely because it is inexpensive. It is
appropriate only after common mean/time/channel effects are controlled or shown
negligible by the frozen diagnostic. Removing one pooled mean alone is insufficient
when satellite time coverage differs. A significant shared residual should prompt
a clock-model investigation rather than being hidden in contrasts.

### Precision and outlier caveats

Equal pair weights are a useful explicit baseline, not a claim that all pairs
have identical independent noise. Closely spaced pairs are correlated, so raw
counts can overstate information and weaken shrinkage. Do not normalize by
arbitrary density counts without evidence; earlier density weighting failed.
Use a globally frozen pair-noise scale and, if needed, a bounded temporal
aggregation rule established from development data. No per-scan prior choice
based on position error is allowed. The previously proposed10/30/60Hz prior
widths remain research hypotheses, with zero as the exact nesting control.

Robust paired summaries are valuable diagnostics. Adding iterative robust
reweighting or clipping immediately would confound the first test. First check
whether a small number of alias-boundary or mismatched-component pairs dominate
the estimate; retain explicit failures rather than silently deleting them.

## Applying a frozen correction

Add `-d_k/2` to RX0's candidate-k frequency prediction and `+d_k/2` to RX1's.
The sign follows the definition `q = RX1 minus RX0 residual`. Since d is frozen,
it introduces no new position, timing, clock, or RF derivatives. Existing likelihood
gradients change only through the residuals and responsibilities. At most one
receiver-sign multiply and satellite lookup is added per observation/candidate;
orbit prediction and nonlinear fitting retain their existing cost.

A frozen estimate is computationally cheaper but statistically different from
the joint model: it cannot revise its contrasts as assignments or position change,
and treating estimated corrections as exact understates their uncertainty. It
does not automatically improve position accuracy. Do not count the pair data
again as an extra independent likelihood term while also keeping their original
observations unless the dependence is modeled explicitly.

If a joint version is later justified, the parameter block still has a simple
analytic gradient. For zero-sum basis U and receiver sign `z=(-1,+1)`, the gradient
is U-transpose times `sum_i(prediction_gradient_ik * z_receiver_i / 2)`, plus
the Gaussian-prior gradient. That costs O(NK) accumulation plus the basis
projection per iteration and adds K−1 optimizer variables. The resulting extra
nonlinear iterations, conditioning and memory matter more than this derivative's
arithmetic. A constrained coordinate representation or profiling a linear block
may avoid a dense basis, but the mixture responsibilities make a one-shot
least-squares elimination inexact for the full likelihood.

## Minimal controlled experiment after the audit

Freeze the numerical policy and all source/input hashes before new fits. Use
ordinary B7 endpoints and the same eligibility, observations, banks and budgets
for these comparisons:

1. Same-start B7 refit with exact zero contrasts.
2. Frozen background-projected paired-shrinkage corrections followed by one
   same-start B7 refit; use the simpler paired-mean formula only if its common-
   effect adequacy criterion was frozen and passed.
3. Only if warranted, the joint contrast model initialized at zero, with the
   same prior and a matched compute-control refit. Do not assume the more
   expensive variant is the preferred deployment candidate.

For each configuration run both c0 and fitted-c, keeping static c and RF-time
coefficients locked in c0. To isolate the c ablation, freeze the same paired
contrast estimate across arms using the ordinary fitted-derived state and
disclose that conditioning; recomputing different contrasts by arm is a separate
end-to-end experiment. An optional cross-fitting diagnostic can estimate
contrasts on one time block and check prediction on another, but it is not a
substitute for randomized whole-recording validation.

Retain all148 consumed DS16/17/18 members, explicit no-ops, failures and prescribed
fallbacks. Report position mean/median/p95/worst, paired regressions, frequency
fit separately, convergence, added wall time and peak memory. Compare the smallest
useful improvement against the cost of another nuisance block. A slightly worse
accuracy result may be acceptable only under an explicit user-approved engineering
tradeoff; it must not be relabeled an accuracy improvement or proof of the0.4km goal.

Candidate selection remains global on development evidence. Independent claims
require a frozen policy and randomized whole-group validation with exposure
auditing. Reference coordinates are evaluation-only. The current post-DS18 reserve
stays closed; production B7 and the frozen iteration87 audit remain unchanged.
