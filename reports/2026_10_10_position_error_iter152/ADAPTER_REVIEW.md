# Exact conditional evaluator feasibility

Source-only review; no objective, recording, quadrature, optimizer or test calls.

## Preconditions for the prepared conditional evaluator

The prepared `conditional.py` constructor validates finite state, smooth-block
layout, precision/design structure, clock boxes and static/RF-time c locks. It
does **not** independently establish full physical feasibility. Before any
recording use, a future adapter must audit the supplied physical vector against
the original prior disk, receiver slope bounds, static-c bounds, common and
coupled satellite timing bounds, interpolation coverage, and applicable local
region constraints. The constructor's successful return is not a substitute for
that audit, nor evidence of a stationary fitted endpoint.

Receiver-disjoint design and precision checks establish the intended structure
for the inspected B7 implementation; they do not prove separability of an
arbitrary supplied `evaluate_joint` callback. Before production-model use,
validate anchor parity, scalar gradients and the two-axis additive identity
against the actual wrapped-likelihood callback while preserving all fixed
penalties. The prepared synthetic callback tests cannot establish that actual
model equivalence. They remain unexecuted while both numerical slots are
occupied by iteration 154. No recording adapter, model execution or quadrature
is authorized by these preconditions.

## Source mapping

The lean first adapter should call the existing final model's
`evaluate_joint(vector, clock)` rather than replace its likelihood with the
prepared finite-Gaussian helper.

[DynamicRFObjective](../../src/leo/analysis/hard60_dynamic_rf.py) constructs two
receiver-disjoint smooth blocks, followed by RF-time coefficients.
[SatelliteCorrection](../../src/leo/analysis/hard60_satellite_correction.py)
inserts satellite coefficients after `smooth_clock_count`, preserving the smooth
precision and placing RF-time last. [SlopePrior](../../src/leo/analysis/hard60_slope_prior.py)
changes only the satellite-slope precision. Use the actual final object's
`evaluate_joint`, not its base class method, so satellite corrections and their
penalties remain included.

Let `m = smooth_clock_count / 2`. Read the actual precision's leading `m × m`
block and require the documented proper, isolated lowest eigenmode `(lambda,q)`.
Verify equal receiver blocks, no cross-block precision, and receiver-disjoint
design support before asserting factorization. Reject an empty or ambiguous
mode; never resolve it with residuals or reference position. Proper prior
precision makes the conditional integral defined even if likelihood information
is weak; it does not establish geometric identifiability or localization benefit.

At the unchanged original endpoint, split each receiver block as
`b_r = b_perp,r + q*a_r`. A trial changes only that smooth block to
`b_perp,r + q*a`, keeping the full physical vector and every other clock entry
fixed. The method returns `(value, physical_gradient, clock_gradient, terms)`;
the exact amplitude derivative is `q.T @ clock_gradient[receiver_slice]`.
Fresh copies avoid shared-state mutation. Both final c arms use the same mode
policy; static c and last-two RF-time locks remain unchanged.

The optimizer bounds original smooth coefficients to ±2000; intersect these
inequalities with the line to obtain the exact finite amplitude interval.
Reject invalid dimensions, nonfinite values, empty intervals or violated fixed
coefficients. Do not impose an arbitrary mode-width bound, infer the interval
from eigenvalue alone, or normalize by its conditional prior mass.

## Preserve normalization and fixed penalties once

Choose the original amplitudes `a*` as an in-domain anchor and evaluate
`F* = F(a0*,a1*)`. Define two scalar callbacks using the same full objective:

`D_r(a) = F(a, other_receiver_at_anchor) - F*`.

Receiver separation implies `F(a0,a1) = F* + D_0(a0) + D_1(a1)`.
Each callback already includes its changing quadratic prior. With
`I_r = integral_interval exp(-D_r(a)) da`, the normalized selected-prior
conditional marginal negative log score is

`F_marginal = F* - log(I_0) - log(I_1) - log(lambda/(2*pi))`.

Do not multiply by a Gaussian prior again inside these integrals. Timing,
satellite and fixed-clock penalties, clutter and detection factors are already
retained once through `F*`. Only the selected Gaussian prior normalization is
added explicitly; omitted full-model constants are common only under the same
model/bank/block policy. Numerically shifted log integrands are necessary, but
any shift must be accounted for algebraically rather than clipping exponentials.

The matching conditional profile score is
`F* + min(D_0) + min(D_1)` over the same intervals. The archived joint fit is not
automatically the conditional minimum at every future spatial stencil point.
Neither multimodal minimum search nor quadrature accuracy is established by this
source review; their bounded coverage and stopping rules require a later freeze.

## Why the finite-mixture helper is not a production adapter

[hard60_score.likelihood](../../src/leo/analysis/hard60_score.py) uses circular
residuals at the ordinary 125 Hz width, a nearest wrapped image justified by
positive clutter, `q = detection_budget / satellite_count`, visible satellite
weights `q/(1-q)`, and conditioned detection normalization involving
`log_p0 = -clutter_rate + visible_count*log(1-q)`. Larger widths use the existing
singleton fallback. A generic normalized finite Gaussian mixture need not
reproduce these conventions, alias seams or detection factors.

For these smooth amplitudes, satellite predictions all receive the same
receiver-row clock shift. Geometry, timing, visibility and bank size stay fixed,
so detection normalization is amplitude-constant. Responsibilities, clutter
competition and winding can still vary. Calling the existing objective preserves
all of this without reimplementing signal weights or winding conventions.
The finite-mixture helper remains useful as a mathematical oracle, not evidence
of actual-model parity.

Full objective calls repeat orbital prediction and physical derivatives, so this
initial exact callback may be too costly for broad quadrature. Cost is unmeasured.
Only after exact callback parity is established should a cached fixed-geometry
implementation reuse production likelihood calls; that is an optimization, not
a prerequisite to this feasibility result. Existing 152 stop conditions and
matched-c requirements remain unchanged. No runtime adapter or experiment is
authorized by this note.

## Subsequent synthetic checks

After iteration 154 shard 0 sealed all 24 cells and its worker processes exited,
root ran `test_conditional.py` in the freed slot while shard 1 continued. The
pinned 47e interpreter, single-thread numerical libraries, disabled pytest plugin
autoload and cache produced **11 passed in 0.14s**. These checks exercise a fake
Gaussian objective: scalar factorization/gradients, prior normalization, unchanged
state, invalid structure/locks/bounds and callback mutation isolation. No recording,
reference coordinate, real likelihood call, quadrature or localization fit ran.
Actual-model parity and bounded integration remain unverified.
