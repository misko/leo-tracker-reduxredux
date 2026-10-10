# Stronger bounded conditional integration: source-only proposal

No recordings, objective evaluations, fits, quadrature, or numerical tests were
performed for this note. The exact wrapped mixture and the two prior-selected,
receiver-specific modes remain those in conditional.py. All geometry, timing,
other clock coefficients, candidate banks, visibility and c locks stay fixed.
The measured callback cost motivates a bounded oracle, not an accuracy claim.

The lean next candidate is **cellwise quadratic envelopes using the scalar value
and gradient already returned by the exact callback**. Keep the same complete
finite support, combined 1e-4 log-integral-width target, 512 value calls per
receiver, and explicit budget-exhausted result. The global Lipschitz construction
remains a valid fallback envelope; an empirical adaptive integrator's agreement
does not replace coverage.

## Curvature bounds supplied by positive clutter

At fixed geometry, write one row's density as

`T_i(a) = b + Σ_j A_ij exp(-r_ij(a)^2 / (2 σ²))`,

where `b=clutter_rate/P>0`, visible `A_ij` are fixed nonnegative amplitudes, and
within a winding interval `r_ij'=-d_i`. Define `ρ_i=Σ_j A_ij/b`, and let W denote
the nonnegative Lambert W function. For `L=-D`, the smooth-interval identity is

`(log T_i)'' = d_i² [ E_w(r²)/σ⁴ - E_w(r)²/σ⁴ - E_w(1)/σ² ]`.

Here w denotes signal responsibilities; clutter has zero score and curvature.
Consequently, with `H=λ+Σ_i d_i²/σ²`,

`L'' >= -H`.

A positive-clutter upper bound avoids the enormous `P²/σ⁴` term:

`L'' <= U = -λ + Σ_i (2 d_i²/σ²) W(ρ_i exp(-3/2))`.

To see this, drop the nonpositive squared-score term and bound each row's
`Σ s_j (r_j²/σ²-1)/(b+Σ s_j)`. Its largest value over independent residuals is
at most `max_t ρ exp(-t)(2t-1)/(1+ρ exp(-t)) = 2W(ρ exp(-3/2))`, with
`t=r²/(2σ²)`. The fractional bound follows by applying the maximizing scalar
ratio to every component after splitting the clutter as
`b_j = b*A_ij/sum_j(A_ij)`. Each nonzero component then has the same peak/clutter
ratio rho. Its numerator is bounded by the common maximum times `(b_j+s_j)`;
summing restores the original denominator. A zero-amplitude component contributes
nothing and a zero-visible row is handled separately. Actual
residuals share one amplitude and cannot exceed this larger independent-residual
domain. This is an analytic bound, not a measured curvature or fixed-label
approximation. A zero-visible row contributes zero.

The bound can still be loose for many rows. A narrower cell can improve U using
the actual fixed residual ranges. Bound each Gaussian's density and second
derivative over that range, including the critical residuals 0 and ±√3σ for
the second derivative. Obtain `T_min>=b`, `T_max`, and `V_max>=T''`. Then
`(log T)'' <= V_max/T_min` for nonnegative V_max, or `V_max/T_max` when negative;
dropping the squared-score term remains conservative. Subtract the exact λ.
This needs source-bound fixed residual/visibility evidence, not another fit or
frozen responsibilities. If obtaining that evidence requires a new scalar cache,
defer it until a separately reviewed exact-callback parity port exists.

## A cell bound that uses the gradient

For a smooth cell centered at c with x in [-h,h], obtain `L(c)` and
`g=L'(c)` from the same callback. The lower and upper functions are

`Q_lower(x)=L(c)+g x-H x²/2`,

`Q_upper(x)=L(c)+g x+U x²/2`.

Integrating their exponentials bounds the complete cell integral. Concave
quadratics have Gaussian-CDF integrals; convex ones require a stable finite
erfi/log-integral implementation. A simpler first implementation can avoid that
additional special-function work: integrate the affine exponential exactly and
multiply by `exp(-Hh²/2)` and `exp(max(U,0)h²/2)`. The log width is then bounded
by `(H+max(U,0))h²/2`, rather than the Lipschitz bound's `2Gh`. Retain the tighter
of independently valid envelopes. Exact quadratic integration can be a later
source-reviewed improvement if this simpler bound proves insufficient.

Sum all cell bounds in log space and refine by the largest absolute integral
gap, with coordinate tie order. The gradient is not an extra value evaluation.
Large g does not itself enlarge the Taylor remainder; monotone tails can therefore
be much cheaper than under a value-only bound. The upper bounds still cover
unvisited remote modes. No prior-standard-deviation cutoff is substituted for
the declared coefficient box.

## Wrapped seams and tails are part of coverage

The nearest-image production branch is continuous but has an upward derivative
jump at a wrap seam. A finite smooth upper-curvature bound alone therefore does
**not** cover a cell crossing that seam. Either split at the exact residual seam
amplitudes or add an explicit bounded jump contribution to the Taylor upper
envelope. One conservative row jump bound is

`J_i <= |d_i| P ρ_i exp(-P²/(8σ²))/σ²`.

Here rho already sums the components. Multiply by an upper bound on the maximum
number of seams crossed by any one component along an anchor-to-point segment;
using the sum of all component seam counts is safe but looser. A boolean saying
the row crosses some seam is insufficient when a component crosses several.
Bound each jump's remainder by its magnitude times traversal distance, at most
h for a cell of half-width h. Positive jumps require this upper correction on
both sides of the anchor; they do not invalidate the lower curvature envelope. The
smallness of this expression in the narrow-sigma branch does not justify silently
setting it to zero or assuming smoothness. If a floating-point underflow argument
is used instead, it must be a documented certificate for the actual executed
branch, not a claim about the mathematical Gaussian. Seam inventory can also be
too expensive; stop rather than omit it.

An independent tail envelope is available from `b<=T_i<=b+ΣA_ij` and the exact
Gaussian prior in a. It bounds whole finite tail-cell integrals analytically.
This can avoid calls in provably negligible cells, but its product over many
rows may be uselessly loose. Tail cells remain in the upper/lower sums; no
outcome-dependent truncation or chosen-mode neighborhood is allowed.

## Decision before an integration freeze

Proceed only to source/synthetic checks of these inequalities and stable cell
arithmetic. Then predeclare a single endpoint diagnostic using the same 24
consumed endpoints and both c arms, complete support and fixed resource caps.
The ~6 ms callback observation makes about 1,024 calls per endpoint plausible in
wall time; it does not show that any coverage certificate reaches 1e-4. Record
every call, construction, derivative, seam and tail-bound cost.

If the analytic envelope remains wider than target at the cap, return
uncertified/budget-exhausted and stop this integration route. A successful
certificate concerns only the specified conditional integral; it supplies no
positioning improvement or independent validation. Ordinary floating-point
arithmetic also requires outward error allowances. Without bounded numerical
error, label the result a conservative numerical envelope, not a formally
rigorous implementation certificate. Adaptive Gauss-Kronrod, grid agreement,
or mode searches may be descriptive checks, but none independently proves that
remote narrow modes were covered.
