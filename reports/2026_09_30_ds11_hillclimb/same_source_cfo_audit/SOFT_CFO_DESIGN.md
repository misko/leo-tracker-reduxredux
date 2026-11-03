# Prospective disjoint-fragment soft-CFO design

Status: design only.  Do not implement or fit while the all-observations screen
has priority.

## Scientific scope

The earlier soft-lane model is a negative result for a different hypothesis.  It
gave every track in one recording/receiver/exact-RF lane a common fitted lane
mean, even when tracks selected different NORADs.  Fixed 3 and 10 kHz widths
worsened aggregate held score and did not consistently improve position.

The new training-only audit isolates 76 disjoint pairs whose two tracks select
the same NORAD with posterior at least 0.90, on the same receiver and exact RF.
Their native, alias-wrapped CFO disagreement is 338 Hz median and 1,273 Hz P90;
66/76 are more coherent than geometry-matched different-NORAD controls.  Each
pair spans a median 57.64 seconds.  This supports one fixed **1,000 Hz** robust
coupling width.  It does not support a width sweep, a hard common CFO, coupling
shared-visit tracks, coupling different NORADs, or coupling receivers.

Freeze pair membership, training support classification, candidate-NORAD maps,
and the 0.90 identity threshold from the original IID endpoint before fitting.
Retain all tracks.  Tracks outside the 76 pairs, including the 22 shared-visit
pairs and all ambiguous tracks, use the original IID likelihood unchanged.

## Two nested comparisons

A geographic change from joining two tracks can come from requiring a common
satellite identity even when their CFOs remain independent.  That effect must
not be attributed to CFO coupling.

For each frozen pair `g=(a,b)`, let `N_g` be the intersection of the two retained
candidate NORAD sets.  The audit finds 2--8 common identities per pair, median 5,
so no pair is reduced to its training-MAP identity.  Use two nested models:

1. **Identity-only control.** Draw one latent NORAD from the causal catalogue and
   mix over every `n in N_g`; retain a separate profiled CFO for each track.
2. **Identity plus soft CFO.** Use the identical common-NORAD mixture and add the
   fixed 1,000 Hz wrapped coupling factor between the two profiled CFOs.

For catalogue size `C`, the mathematically normalized pair mixture uses one
common catalogue draw,

```text
L_identity(g) = (1/C) sum[n in N_g] L_a,n L_b,n .
```

Candidates absent from either retained bank contribute zero; they must never be
silently replaced by a fallback denominator.  At a trial position, a term is
finite only when that common candidate is visible for both tracks.  An empty
common visible set is an explicit model-domain failure.  The full candidate
mixture is retained over `N_g`; the selected training-MAP slot is not fixed.

The original IID result remains the external incumbent.  The identity-only
control identifies the effect of the common-identity assertion.  The difference
between soft-CFO and identity-only isolates the CFO penalty.  Raw training scores
from the one-draw pair model and the two-independent-draw IID model are not
directly comparable because their catalogue denominators differ; held
full-minus-training scores and geographic errors remain comparable.

## Offset likelihood and alias convention

For common candidate `n`, let training residuals in canonical 11.2 GHz units be
`r_tn(x)`, canonical track CFO be `b_t`, observation scale `s=100 Hz`, and the
unchanged weak individual prior scale be `sigma_b=1 MHz`.  Preserve the original
per-observation Student-t4 density and individual priors:

```text
ell_tn(b_t; x)
  = sum[i in train(t)] log t4(r_tn,i(x) - b_t; s)
    - b_t^2 / (2 sigma_b^2).
```

For exact RF `f`, set `alpha=f/11.2 GHz`, native alias period
`P=1/4.4 us`, fixed width `gamma=1000 Hz`, `k=2 pi/P`, and
`rho=exp(-k gamma)`.  The normalized wrapped-Cauchy Bayes factor relative to a
uniform circular difference is

```text
W_gamma(d) = (1-rho^2) / (1+rho^2-2 rho cos(k d)),
d = alpha (b_a-b_b).
```

It is periodic and therefore sums over every integer alias branch.  Do not pick,
freeze, or optimize a separate alias integer from a candidate's residuals.  This
candidate-independent wrapping prevents an alias choice from becoming an
unreported identity-dependent degree of freedom.

The coupled candidate score is the highest qualified located stationary profile

```text
q_n(x) = max[b_a,b_b] {
    ell_an(b_a;x) + ell_bn(b_b;x) + log W_gamma(alpha(b_a-b_b))
}.
```

The weak 1 MHz prior remains on each CFO; the coupling supplements rather than
replaces it.  If absolute density normalization is recorded, divide the product
prior by `Z=E[W_gamma(alpha(B_a-B_b))]` for independent
`B_a,B_b ~ N(0,sigma_b^2)`.  `Z` is position- and candidate-independent and is
numerically indistinguishable from one at these scales, but recording it keeps
the probabilistic statement exact.

As `gamma -> infinity`, `rho -> 0` and `W_gamma -> 1`.  The coupled score,
profiled offsets, envelope gradient, candidate responsibilities, and held score
must then reproduce the identity-only control to numerical tolerance.  With no
frozen pairs, the identity-only implementation must reproduce original IID
scores and gradients exactly.

## Profile and envelope gradient

The two CFOs must be optimized jointly for every common candidate.  Writing
`h(d)=d log W/dd`,

```text
h(d) = -2 rho k sin(k d) / (1+rho^2-2 rho cos(k d)),

0 = sum_i 5(r_ai-b_a)/(4s^2+(r_ai-b_a)^2)
    - b_a/sigma_b^2 + alpha h(d),

0 = sum_i 5(r_bi-b_b)/(4s^2+(r_bi-b_b)^2)
    - b_b/sigma_b^2 - alpha h(d).
```

The Student-t and wrapped terms are multimodal.  Batched independent-track IRLS
solutions provide starts, supplemented by coupling-projected starts around the
nearest circular equality and any distinct independent stationary modes.  Refine
each start with a two-dimensional root/Newton solve, reject roots whose gradient
or negative-curvature checks fail, and select the highest objective among the
located qualified stationary maxima.  This finite search does not certify a
global two-dimensional maximum and must not be reported as one.  A single local
solve is insufficient.  The profile audit must record scalar modes, starts,
distinct roots, selected objective, terminal gradient and Hessian eigenvalue for
every candidate.

At a verified stationary maximum the envelope theorem removes derivatives of
`b_a*(x),b_b*(x)`.  For geometry coordinate `x_m`, the candidate gradient is

```text
d q_n/d x_m = sum[t in {a,b}] sum_i
  5(r_tn,i-b_t)/(4s^2+(r_tn,i-b_t)^2) * d prediction_tn,i/d x_m.
```

The coupling has no additional direct geometry derivative because exact RF and
the circular difference are fixed and its offset derivatives vanish jointly at
the profile.  Mix these candidate gradients with log-sum-exp responsibilities.
Unpaired-track gradients remain byte-for-byte original.  Finite differences
must preserve the visible common-candidate set; a visibility change invalidates
that local derivative audit rather than being silently renormalized.

Held scoring profiles offsets on training observations only, freezes those
offsets and fitted geography/timing, and evaluates full minus training density.
Held values must not select a root, identity, pair, alias treatment, or width.

## Numerical budget and tests

There are only about 2.4 eligible pairs per scan and a median five common
candidates per pair.  A screen scan therefore adds roughly 12 two-dimensional
profiles to the existing batched likelihood.  Cache prediction geometry and
independent CFO starts, batch residual/derivative evaluation across candidates,
and run BLAS1.  Require a timed synthetic plus one frozen screen-index evaluation
before launch; reject the implementation if projected per-fit time exceeds the
90-second cap.  No quadrature is required.

To bound work, rank each Cartesian scalar-mode combination by its two independent
profile scores.  Retain it as a joint start only when that sum plus the maximum
possible wrapped log factor can exceed the best already evaluated feasible joint
point.  This is a fixed start-selection rule.  The subsequent root solver is
unconstrained and can cross a nominal scalar basin, so discarded starts are not a
proof that no better two-dimensional root exists.  Report both the combinations
removed and the finite-search limitation; never describe this as certified global
pruning.

Required preparation tests:

- `gamma=infinity` reproduces identity-only score, gradients, offsets and held
  score; no-pair identity control reproduces original IID exactly.
- The wrapped coupling factor and its first two derivatives are invariant to an
  integer native alias shift, and swapping the two tracks is symmetric.  The full
  profile retains the original weak nonperiodic 1 MHz CFO priors, whose explicit
  prior term can change under an alias shift.
- Joint profile agrees with a dense/brute reference on synthetic multimode cases
  and finds the best of deliberately separated stationary modes.
- Analytic envelope gradients agree with finite differences away from visibility
  boundaries and alias half-period ties.
- Every input track appears exactly once; shared-visit, cross-receiver,
  different-RF and ambiguous tracks remain independent.
- Common candidate intersection, catalogue denominator, visibility failure, and
  candidate ordering are tested explicitly.
- Changing held samples cannot change training score, roots, responsibilities or
  gradients.

## Decision and conditioning risks

The science justifies one fixed-width treatment arm, `gamma=1000 Hz`, only if the
identity-only control is evaluated alongside it.  It does not justify a width
sweep.  A treatment-versus-IID result alone is uninterpretable because the shared
identity mixture can move the estimate without any CFO information.  The control
can share the same predictions and independent CFO profiles, so it is a required
diagnostic rather than another tuned family.

The largest risk is training reuse: pair membership, identity confidence,
disjoint support, and the 1 kHz width all came from original32 training residuals,
which the proposed model would fit again.  Any original32 win is therefore
exploratory and requires the already frozen additional panel or another untouched
panel before promotion.  Other material risks are conditional, possibly wrong
NORAD labels; candidate-bank intersection truncation; baseline geometry error
masquerading as CFO coherence; and optimizer attraction to the baseline identity
basin.  The periodic factor avoids candidate-dependent alias leakage, while the
identity-only control exposes improvement caused by stronger association rather
than CFO physics.

Keep this design queued behind the all-observations screen.  Do not launch it
unless that higher-priority family is rejected or the coordinator explicitly
requests this alternative.
