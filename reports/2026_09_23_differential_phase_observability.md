# Differential-phase observability after two-source isolation

The stream-1 28.200 s snippet is a development check for coefficient-phase
measurement. It is not association, direction, speed, or position evidence.
Its near-zero shared-CFO closure is conditional 20 ms model adequacy, not a
physical common-LO measurement ([nested result](2026_09_23_shared_cfo_nested_results.md)).

## Coefficient gauge

The frozen isolation replay creates eight known-pilot columns per source, with
independently rounded frame starts and a CFO term referenced to the common chunk
sample index ([template construction](../tools/research/replay_joint_pilot_isolation.py)).
For receiver `r`, source `s`, and tone `q`, an unconstrained local fit is

`x_r[n] ≈ sum_(s,q) c_(r,s,q)(t) T_(s,q)[n] exp(j 2π δf_(r,s)n/Fs) + e_r[n]`.

The published 16 coefficients are constant least-squares amplitudes over an
entire 20 ms training mask, then reused for response SSE. They are not a phase
time series. The shared-CFO arm constrains receiver frequency arrays. Neither
can establish local phase stability; a new extraction must not inherit either
constraint.

`arg(c_(1,s,q)c*_(0,s,q))` is only a coefficient gauge after separate
receiver/source NCO demodulations. It is not yet the cross-receiver phase at
time `t`. Reconstruct each fitted component at its physical group centre,
`v_(r,s,q)(t)=c_(r,s,q) T_(r,s,q)(t; epoch, nominal_CFO) exp(j 2π deltaf_(r,s)t)`,
then remove or transport the known pilot modulation to one canonical source
gauge. Only then form `D_(s,q)(t)=arg(v_(1,s,q)v*_(0,s,q))`. This restores both
the nominal template-CFO and residual-CFO phase differences that the separate
demodulations removed.

With correct transport and source epoch, `D` removes transmitted pilot phase,
but retains approximately

`D_(s,q) = (2π f_s/c) b·u_s(t) + [theta_1(f_(s,q),t)-theta_0(f_(s,q),t)] + eps_(s,q)`.

The `theta` term includes LO, cable, LNB, sample-clock, and frequency-response
phase. Preserve tone index: frequency-dependent differential delay is a real
nuisance.

## What cancellation permits

The candidate same-tone, common-time double-difference increment is

`M_q(t)=wrap([D_(a,q)(t)-D_(b,q)(t)]-[D_(a,q)(t0)-D_(b,q)(t0)])`.

Its geometry is the corresponding increment of `(2π/c)b·(f_a u_a-f_b u_b)`.
Independent LNBs do not automatically invalidate cancellation: a receiver LO
phase cancels algebraically if shared across both simultaneous signals. That
must be tested, not assumed. Unequal carrier frequencies, frequency-dependent
receiver response, changing group delay, alias error, or LO evolution between
noncontemporaneous estimates remains. The `t0` reference removes static
per-tone phase only. Average tones only after their separate `M_q` trajectories
agree.

## Valid local development extraction

Keep source timing, edge, nominal CFO, and raw-index gauge frozen. In each
guarded physical time group, estimate all 16 coefficients with independent
source-by-receiver CFO nuisances. Do not impose shared CFO, shared phase,
cross-receiver coefficients, or cross-source coefficients. Fit nuisances on
calibration samples only; score coefficients on disjoint response samples.
Reject rank-deficient, boundary-CFO, or low-coherence groups. Require per-tone
reconstruction, held-IQ mutation, rolled-pilot, and swapped-epoch controls.

A training reference vector per receiver/source fixes an arbitrary intercept.
It supports held phase changes, not an absolute double difference. A circular
affine intercept and slope fit removes double-difference phase rate too, so its
held residual tests conditional stability or curvature over 20 ms, not velocity.

The proposed `20260929` mask is valid only because this is chronological
probe index 4 and the frozen nested fit used `20260925 + 4`, hence the same
split. Verify the old and new train/held index hashes before reuse and label
the result a conditional reanalysis. A different mask would require all four
independent CFOs to be refit from its training groups only.

## Next association test

Use a predeclared, phase-blind population of multi-second simultaneous
two-source intervals. Assign seeded random **whole intervals** to outer train
and held sets before IQ access, keeping receivers, sources, and failures
together. On training intervals fit an effective three-component baseline and
a predeclared low-order common differential-LO term with static per-tone
intercepts, after a full-rank line-of-sight check. Predict wrapped `M_q`
increments on untouched held intervals. Compare the same held response with
wrong-time TLEs, source-pair permutations, swapped epochs, and rolled pilots.

This can test candidate-pair differential-phase compatibility after stated
nuisances. A full-rank effective-baseline fit with untouched held prediction can
be informative even without a surveyed baseline orientation. It does not by
itself identify physical baseline orientation, receiver pose, satellite
direction, velocity, or position; those interpretations need independent
timing, frequency-response, baseline, and common-state calibration authority.
