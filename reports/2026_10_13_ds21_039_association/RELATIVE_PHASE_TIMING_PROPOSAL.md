# Separate relative satellite phase from the common receive epoch

Proposed next timing test: compare the original receive-epoch retiming with a
relative satellite-phase convention, after synthetic qualification. This is a
mechanism sensitivity, not a correction supported by measured orbit errors.
There is no new DS21 inference or localization result here.

The saved [factorial](TIMING_CALIBRATION_FACTORIAL_RESULTS.md) shows timing
compensating 99.5–99.9% of the prescribed weak-direction geography-only NLL
increase. Fully adjusted states keep endpoint visibility and sampling integers.
It establishes confounding, without identifying its physical source. The
[UTC audit](../2026_10_13_ds21_039_root_cause/UTC_TIMING_PROVENANCE.md) supplies
no independent absolute-clock attestation or conversion error. Neither result
justifies narrower timing priors.

## Physical convention and falsifiable hypothesis

Let `T=t+u` be the shared receive epoch and `q_k=T+d_k` the satellite phase
epoch, with the existing zero-sum relative shifts `d=B beta`. Let `G(t)` be
the repository TEME-to-ECEF rotation and `Omega` its Earth rotation vector.
Current scoring evaluates the already-ECEF bank at `q_k`:

```
r_epoch = G(q_k) r_TEME(q_k)
v_epoch = G(q_k) v_TEME(q_k) - Omega cross r_epoch
```

That is a coherent epoch-retiming model. It also assigns a separate Earth
orientation to every satellite's relative timing. A different physical
mechanism, satellite phase uncertainty at a common receive epoch, is:

```
r_phase = G(T) r_TEME(q_k)
v_phase = G(T) v_TEME(q_k) - Omega cross r_phase
A = G(T) G(q_k).T
(r_phase, v_phase) = (A r_epoch, A v_epoch)
```

Rotating both arrays is essential. Because `A` rotates about the same z axis
as `Omega`, the velocity rotation also preserves the required ground-relative
`-Omega cross r` term. Rotating position alone is incorrect. The shared `u`
continues shifting the common physical epoch, including Earth orientation;
`d_k` changes satellite phase at that shared orientation. It is not a general
orbit-error model or a measured along-track correction.

Expected signature: the difference vanishes for `d=0` at any `u`, and in the
zero-Earth-rotation limit. For small `d`, the extra state rotation has leading
terms `Omega cross r * d` and `Omega cross v * d`. This changes relative-timing
derivatives without deleting timing parameters or increasing their penalty.
If the geographic compensation remains essentially unchanged, conflating these
mechanisms is not a useful explanation of the observed weak direction. A
different optimum or a smaller residual alone would not identify a physical
clock or TLE error.

## Isolated component and synthetic qualification

New pure component: `src/leo/analysis/research/relative_phase_timing.py`.
`phase_retime_ecef` rotates existing ECEF position and velocity using explicit
receive/query sidereal angles. `phase_retime_tangent` applies the full chain
rule, including actual interpolation state derivatives. It does not assume
interpolated position derivative equals stored velocity. Common-time derivatives
must include both angle derivatives; relative-time derivatives hold the receive
angle fixed. No original scorer, kernel, frame conversion or prior is changed.

Owned tests use independent analytic circular TEME orbits. They check direct
frame-conversion equality, velocity consistency, exact `d=0` closure, both timing
derivatives against finite differences, explicit invalid shapes, and a degenerate
equatorial example with an exact longitude/common-time gauge. That last test
preserves non-identifiability rather than reporting artificial position recovery.

The two noiseless recovery controls generate synthetic data separately under the
epoch and phase conventions, using six distinct orbital planes, an invented
geography, nonzero zero-sum relative shifts, receiver offsets/drifts and a fitted
RF coefficient. Each matching convention must recover its generating geography
and nuisance parameters. At identical parameters, the other convention must give
detectably different frequencies. These tiny known-ID tests qualify forward and
inverse mechanics; they do not establish recovery with DS21's unknown satellite
identities, short scan span, clutter or sampling ambiguities. They do not assert
that the wrong convention cannot absorb a discrepancy at another optimum.

## Subsequent DS21 control requires separate implementation review and frozen protocol

Keep the original receive-epoch scorer as the matched control. Preserve all
native candidates, satellite bank, waveform/clutter/visibility normalization,
original per-view calibration frames, fitted `c`, zero-sum basis, existing timing
priors (common 3 s, relative 2 s), physical bounds and local disks. The original
and refined training-selected starts must be identical between conventions;
neither condition may start from the other's fitted endpoints. A first matched
CH1–4 / CH5–8 / CH1–8 comparison would require at most 12 calls: two starts per
view and convention, 20 seconds / 600 iterations each, within a frozen bounded
slice. Exact saved-source objective/gradient replay precedes any fitting.

Use the existing reproducible randomized whole-block partition without creating
a chronological holdout. Select by training only; report held-block likelihood
separately from post-seal position error. Retain failures, all view results,
weak-direction compensation and posterior/support changes. Promotion requires
subsequent fixed-rule development transfer and the untouched locked release
sequence; there is no reference-selected prior, direction, timing convention or
per-recording winner. Numerical execution follows implementation review and the
root-owned frozen protocol; this proposal itself does not start a run.
