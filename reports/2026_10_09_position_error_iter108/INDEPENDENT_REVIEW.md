# Independent persistence-kernel review

Source/derivation review and synthetic tests only. No recording loader, position
fit, reference-coordinate access or production edit performed. The six provided
kernel tests pass in the existing scientific environment (1.43s).

**No blocking mathematical error found in the synthetic kernel.** Forward and
backward recursions agree with the stated normalized transition, and exhaustive
tiny-sequence enumeration checks score and smoothed occupancies independently.
Finite differences agree with the occupancy-weighted frequency derivatives.

## Checked mathematical points

- The visibility mask applies to the retained previous identity at the *current*
  row. A disappearing satellite and clutter both redraw from current pi, as
  specified. Invisible signal states receive neither redraw nor sticky mass.
- The scalar reset mass and backward redraw inner product implement the dense
  transition in O(NK), without allocating a transition matrix in the kernel.
  Segment-start boundaries stop backward messages as well as forward persistence.
- Detection normalization D remains in the score. The categorical normalization
  alone would be insufficient; this implementation retains the original visible-
  satellite-count factor and finite clutter floor.
- At rho0, exact returned score/gradient/occupancy equal hard60's independent
  likelihood, including its floating-point evaluation order. The separate
  algebraic test also checks nesting without relying only on that return shortcut.
- Away from visibility/circular-wrap boundaries, smoothed occupancy is the correct
  derivative of the marginalized sequence likelihood with respect to emissions;
  no derivative of occupancy should be added to the first gradient. Visibility
  boundaries remain nondifferentiable, just as the independent scorer.

## Limits to preserve before a recording adapter

The proposed rho is a per-window identity-persistence probability, **not** an
estimated RF residual-correlation coefficient or continuous-time correlation
scale. Unequal row spacing/sample rate changes its effective time scale. Clutter
always resetting also means the transition generally does not preserve pi as a
stationary distribution. Thus the model changes both temporal dependence and
sequence identity preference. Those are stated model assumptions, not verified
physical satellite association.

The adapter must deterministically create disjoint, inference-only segments and
reset on receiver/channel/RF/gap boundaries. Every observation occurs exactly once;
uncovered/overlapping tracks must stay independent. The kernel accepts only reset
flags and cannot verify those recording contracts itself. Tests currently exercise
abstract resets, not actual RF/channel metadata. Do not call that integration done.

The returned occupancies are smoothed categorical probabilities, not Gaussian
uncertainty, clock states or calibrated independence. Existing physical/clock
Jacobians can consume prediction_gradient, but actual composed-model finite
differences, unchanged priors/c0 locks and exact rho0 production nesting are still
required before any position experiment. No candidate bank or start should be
derived from reference coordinates or from the new model's evaluation error.

Memory is O(NK) for full forward/backward/occupancy arrays, despite linear time.
Bound short segments before claiming embedded memory cost; independent likelihood
is also computed for every rho, adding a constant-factor pass. Extremely near-one
rho and a large bank can expose subtraction roundoff in1−sticky.sum(). Add a
probability/nonfinite invariant stress test before broad parameter ranges, rather
than silently clipping or renormalizing a different model. Current tested0.999
and long-sequence cases are finite.

One or a few globally predeclared rho values require a separate frozen predictive
and matched-c protocol; the kernel supplies no justification for choosing them.
Compare in-block score, out-of-block predictive evidence and position separately.
Do not compare normalized objectives across rho as an operational winner selector.
Kernel correctness is not evidence of localization gain or independent validation.

## Adapter and no-fit census review

The prepared adapter now supplies disjoint segments from shared bootstrap track
membership, with receiver, channel, exact RF and positive at-most-two-second gap
checks. Overlaps and uncovered observations remain independent; packing is
reversed before gradient comparison. Both archived B7 arms retain their original
endpoints and candidate bank. The c=0 arm checks static c and the two RF clock
coefficients, matching the production clock layout.

Full objective reconstruction includes common timing, relative timing and clock
quadratic priors. New synthetic controls exercise nonzero priors, detect omitted
priors and check prediction composition including satellite, baseline and clock
terms. All 26 kernel, segmentation and adapter tests passed in 1.64 seconds.
These synthetic checks do not replace per-recording saved-objective and gradient
parity assertions; the census records those checks or explicit failures.

The protocol correctly discloses inherited archived-error equality and
reference-bearing artifact digest checks as provenance admission dependencies.
Those values do not guide grouping, geometry, starts or winner selection. Calling
the complete import path wholly free of reference reads would be inaccurate.

The prepared freezer verifies the immutable iteration106 closure, copies all
148 bindings (63 DS16, 51 DS17, 34 DS18), and adds current iteration108 Python and
Markdown sources. It declares rho=0, zero optimizer calls, two single-thread
workers and append-only full membership coverage. It does not substitute the
iteration106 100 Hz fits or recovered endpoints. No blocking issue remains for
freezing this descriptive census. No freezer, recording reconstruction or
recording evaluation was executed during this review.
