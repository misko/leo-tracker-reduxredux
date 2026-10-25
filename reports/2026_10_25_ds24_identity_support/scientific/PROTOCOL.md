# Old12 identity-support and numerical replay

No new observations, identity draws, RF, position fits, parent refits, shortlist
replacement or operational assignments. Reuse all12 original nomination trials
on DS24-0010/0011, both c arms and all192 candidate contexts. Bind the exact old
observation NPZ, covariance/raw NPZ, catalogue/prior inputs and ordinary top8
shortlists. Preserve old scores/outcomes alongside every new attempt. Generating
truth is unavailable to the scoring port and is used only for later reporting.
Original generator/scorer conditioning differences remain; this is a regression
check, not a matching-law simulator or calibration experiment.

The new physical support law multiplies the likelihood by the indicator that
every native source observation has nominal line of sight. Invisible phases
contribute zero under the original normalized Student nu3 prior on[-15,15];
never divide by visible prior mass. This gives joint CFO-plus-visibility-event
evidence, not a silently detected-conditional phase prior. Null and all physical
models retain exactly the original uniform aliases−4,…,+4, 300Hz source constant
and covariance, candidate-specific causal phase location/SD, and3 physical modes.

Support is certified against actual piecewise-linear bank position plus Earth
rotation, with no extrapolation. Verify finite/increasing grids and equality of
nominal/mode knots. Partition at every native timestamp's shifted interpolation
knot; visibility sign and derivative bounds certify sign/monotonic pieces.
Root tolerance1e−11s with explicit floating guards, maximum22 subdivisions;
uncertain tangencies remain unresolved. Retain inner visible support and root
brackets. The full evidence upper bound includes root-bracket contributions;
do not discard uncertain boundary mass. Empty certified support is exactly zero
evidence, distinct from an unknown calculation.

Use the positive Woodbury quadratic norm(w−WBalpha)^2+norm(alpha)^2 and preserve
the determinant/normalization. Primary integration uses public SciPy1.18.1
log-tanh-sinh, log relative target log(1e−9), zero absolute target, levels0…6,
512-phase batches, over every physical interpolation piece. Required references
use independent composite Gauss-Legendre orders32/64 on identical support
pieces. The old absolute1e−3 objective tolerance is unchanged. Original dense
top2, new raw top2 and any evidence-interval winner/null-overlap competitor
require the reference, never backfilled with a more convenient candidate.

Quadrature agreement alone is insufficient: an independently preserved analytic
counterexample makes both rules miss99% of an off-grid Gaussian mixture while
claiming convergence. Therefore enclose the complete physical evidence using
analytic phase-derivative bounds for both mean and physical covariance, every
finite alias and the original Student prior. Bounds use the native minσsqrt2
as a LOWER bound on sqrt(lambda_min(C)), never marginal diagonal SD. Require
range bounded away from0. Log-Lipschitz panel envelopes cover unsampled modes;
include floating margins. Refine largest possible missing mass only, maximum
8192 panels and512 refinements per batch; all work counts against the cap.
Stop with nonqualification if bounds remain too broad. No additional method,
node limit, tolerance, rescue or scientific retry after outputs.

Report TWO separate outcomes. (1) Absolute score precision: the reported primary
objective lies within1e−3 of BOTH ends of the full inner/outer support evidence
enclosure, and required primary/reference comparisons pass. This does not follow
merely from a narrow enclosure width. (2) A best-model ordering certificate may
hold without precise individual scores: one model's lower log evidence must
strictly exceed EVERY competing upper log evidence, including the null and all
eight physical candidates. Unknown bounds block this proof. Null uses the same
proper closed Gaussian model, independently replayed by an eigensolve within
1e−7 objective; a separate1e−6 objective floating allowance bounds its interval.
Empty support is log evidence−infinity. Neither outcome validates identity or
assigns it operationally.

The envelope algorithm may stop early when an upper evidence bound falls below
an already computed model lower bound, initially null, subsequently any earlier
ordinary-shortlist candidate. Use threshold minus log2 separately for inner and
root-bracket mass, then check their actual summed bound. This is certified
exclusion, not precision qualification or a truth-specific early exit.

Two workers/one BLAS/OMP/MKL thread each, maximum600 cumulative scientific
worker-seconds including producer numerical tests. A shared wall deadline uses
half the remaining worker budget conservatively. No post-deadline stage starts.
All12 trials retain terminal/failed statuses even when budget or context fails.
No fresh controls start under this protocol. Independent source/math preflight
and root go are required before the single archived replay.
