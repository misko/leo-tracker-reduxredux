# 1.333 ms frame timing, phase, and Doppler-rate investigation

Date: 2026-08-25

## Decision

The standard analysis architecture should be frequency-first:

1. retain the 20 ms GLRT for detection, frame epoch, source binding, timing
   basin, and the approximately 227.273 kHz CFO alias decision;
2. estimate CFO independently on each complete 750 Hz frame;
3. fit robust Doppler-rate segments to those frame estimates in physical time,
   with a free intercept for every verified RF-contiguous segment; and
4. treat cross-frame carrier phase and eight-tone relative timing as optional
   diagnostics until a separate validation lane proves that either improves
   prediction.

The five-dwell prototype supports making independent frame CFO and local robust
rate a standard *typed, fail-closed measurement*. It does not support feeding
phase or timing back into the standard Doppler-rate product yet. Of 32 complete
locklets, only two post-selection locklets had a fit-withheld odd-Qin phase arc,
and neither phase-derived rate improved fit-withheld odd-Qin CFO. Relative
timing did not improve the result enough to justify promotion.

This is candidate evidence, not a completed production promotion. The upstream
frame-CFO run covered all five frozen dwells but failed 2 of 59 frozen gates:
strong/interior retention was 74.66% for `470384` and 63.06% for T06 against a
75% threshold. The estimator correctly fails closed on rejected frames; the
data do not support promising a universal 75% yield.

## Exact frame timing

The signal cadence is exactly 750 Hz, so “1.3 ms” must be implemented as
1/750 s = 1.333333... ms. At 2.5 MS/s the frame period is 10,000/3 samples:

| frame index | ideal offset | selected offset | selected - ideal |
| ---: | ---: | ---: | ---: |
| 0 | 0.000 | 0 | 0 |
| 1 | 3333.333 | 3333 | -1/3 sample |
| 2 | 6666.667 | 6667 | +1/3 sample |
| 3 | 10000.000 | 10000 | 0 |

The implementation therefore carries a continuous coordinate

`u_m = epoch + m Fs/750 + tau_m`

and selects the integer slice once with `round(u_m)`. It never accumulates
`round(Fs/750)`: doing that at 2.5 MS/s is 20 samples wrong after 60 frames.
The fractional remainder is retained for phase/delay compensation.

Each complete frame contains 302 OFDM symbols at 4.4 us, or 1.3288 ms and 3322
samples at 2.5 MS/s. The 300 known Qin pilot symbols span 1.3200 ms. Their
reference is the mean symbol center, 668.8 us or 1672 samples after the frame
start. Every raw extraction includes one sample of guard on each side.

An acquisition refill with unknown RF elapsed time is a hard boundary. A frame
whose guarded slice crosses that boundary is rejected, and phase/rate fitting
is split there. Stored-contiguous samples are not assumed to be RF-contiguous.

## What is observable

For frame `m`, Qin symbol `i`, and edge tone `k`, the useful local model is

`y[m,i,k] = h[m,k] q[i,k] exp(j 2 pi f[m] t[i]) + noise`.

Profiling the eight complex gains `h[m,k]` makes within-frame CFO observable
without connecting carrier phase between frames. This is why the frame CFO
estimator survives unknown common frame phase and sparse occupancy.

The complex gain phase can be retained after CFO estimation, but its absolute
interpretation is limited:

- a common frame phase is a nuisance by default;
- the observed real data contain a modulo-pi sign family, so phase is modeled
  modulo pi rather than as an unwrapped absolute carrier phase;
- a stable inter-tone phase slope can expose *relative* delay across a locklet,
  but a constant delay is absorbed by the unknown channel vector; and
- receiver clock, transmitter frame clock, propagation delay, and channel
  evolution are mixed in the relative timing rate.

Consequently, the existing `timing_spread_hz` field is only the change in CFO
under a +/-1-sample slice perturbation. It is a useful sensitivity gate, not a
timing estimate, transmit epoch, or pseudorange measurement.

## Implemented model

The prototype exposes two public layers.

`estimate_edge_pilot_frame_complex_split` processes one guarded raw frame. It
profiles residual CFO independently on even and odd Qin symbols and returns the
two complex eight-tone channel vectors in a raw capture-sample phase gauge.
Only the even fold can determine training membership. Guard energy cannot
masquerade as pilot energy, and malformed held-out data cannot change the even
fit or iteration count.

`fit_iterative_frame_phase_rate` processes one continuity-safe locklet:

1. robustly fit `f(t) = f0 + fdot t` from even-Qin frame CFO;
2. optionally fit receiver-relative `tau(t) = tau0 + taudot t` from inter-tone
   channel phase, including the exact `0, -1/3, +1/3` lattice correction;
3. align the eight-tone vectors to a common channel reference;
4. fit modulo-pi carrier-phase residuals for a candidate correction to `f0`
   and `fdot`;
5. update the channel reference and repeat until frequency, rate, timing
   offset, and timing rate all converge;
6. reject a phase arc if the delay grid repeatedly hits its boundary, the
   channel loses similarity, phase residuals are too large, or the phase rate
   disagrees with independent frame CFO; and
7. inspect odd Qin only after membership, parameters, ambiguity bits, and the
   iteration count have frozen.

The primary returned rate always remains the independent even-Qin frame-CFO
rate. A phase arc and a phase-feedback candidate are separate claims. Even a
real phase arc is not permission to alter Doppler rate.

The report also reselects the CFO alias using even-Qin split evidence before
odd validation. All five choices agree with the upstream frame-CFO evaluation.
The six corpus regions were originally ranked with upstream GLRT pilot scores,
however, so the odd lane is post-selection and fit-withheld, not a fully
independent scientific holdout.

## Five-dwell comparison

The comparator is the 20 ms GLRT trajectory trend re-centered independently in
each refill-safe locklet using even-Qin data. Every RMS below is then evaluated
on the same fit-withheld odd-Qin frames. Lower is better. Phase columns show
diagnostic candidates whether or not they passed the phase gates; none was
applied to the primary result.

| dwell | GLRT RMS | frame CFO RMS | phase, timing fixed | phase + relative timing | frame / GLRT | complete locklets | phase arcs | feedback candidates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `470384` | 63.23 Hz | 19.44 Hz | 19.26 Hz | 19.29 Hz | 30.75% | 5 | 0 | 0 |
| T01 | 46.86 Hz | 28.48 Hz | 30.45 Hz | 30.25 Hz | 60.79% | 6 | 0 | 0 |
| T06 | 27.73 Hz | 29.13 Hz | 30.04 Hz | 29.79 Hz | 105.05% | 9 | 0 | 0 |
| T04 | 47.74 Hz | 25.95 Hz | 26.87 Hz | 27.04 Hz | 54.35% | 6 | 2 | 0 |
| T03 | 61.63 Hz | 48.57 Hz | 49.22 Hz | 48.83 Hz | 78.81% | 6 | 0 | 0 |

Frame CFO improves the post-selection odd-Qin RMS on four of five dwells. T06
is 5.05% worse in this shorter locklet comparison and should remain the control
case. The phase candidates are worse than frequency-only on T01, T06, T04, and
T03. `470384` shows a small pooled numerical improvement, but no locklet there
passes the phase-arc gates, so it supplies no phase-feedback evidence.

The two phase arcs are both in T04:

| region role | frames | odd phase RMS | stack efficiency | frame-rate RMS | phase-rate RMS | result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| late median margin | 56 | 0.165 rad | 0.9865 | 26.30 Hz | 27.20 Hz | arc only; rate worsened |
| refill-boundary region, split safely | 28 | 0.073 rad | 0.9977 | 24.22 Hz | 25.48 Hz | arc only; rate worsened |

The median all-complete relative timing-rate candidates range from -5.54 to
+13.22 samples/s, with per-dwell p95 absolute values from 6.46 to 16.78
samples/s. These are not qualified clock estimates. Timing-fixed and
relative-timing phase candidates are nearly indistinguishable in predictive
RMS, so current real data demonstrate no benefit from timing feedback.

## Synthetic and contract evidence

The tests pin the exact fractional lattice, discontinuity handling, modulo-pi
sign state, acquisition-seed-independent phase gauge, even/odd isolation,
timing convergence, delay-grid boundaries, and malformed validation behavior.
An end-to-end 30-frame raw Qin waveform with true rate -1800 Hz/s recovers
-1799.928 Hz/s from independent frame CFO and -1799.990 Hz/s from the optional
phase candidate; odd phase RMS is 0.00292 rad and stack efficiency is
0.9999994. Random independent frame phase is rejected without changing the
primary frequency rate.

The output report verifies the input frame-CFO summary/row digests before use,
records the exact implementation digests, and produces byte-identical summary,
locklet, PNG, and manifest artifacts on repeated full runs.

## Recommended iterative architecture

For a future online or fixed-lag implementation, retain the same separation:

`GLRT top-K source/alias hypotheses -> exact continuous frame lattice -> per-frame profiled likelihood -> robust [f, fdot] update -> optional [tau, taudot] and modulo-pi phase mode -> independent validation -> reset`

The state can be represented as `[f, fdot, tau, taudot]`, with one free CFO
intercept per continuity segment. Preserve multiple acquisition aliases until
timing and Doppler evidence selects a source; never average competing aliases.
Use the whole local per-frame likelihood when available rather than only its
argmax. Carrier phase should have RESET, CONNECTED, and modulo-pi modes, with
RESET as the default. A refill, gap, source change, failed gate, or
reacquisition resets phase/channel/timing state and prevents a rejected phase
innovation from impulsing frequency.

## Remaining work before phase or timing promotion

1. Add a second validation lane whose region selection and feedback decision do
   not use the same odd-Qin observations used to quote improvement.
2. Implement an actual early/late or joint CFO-delay likelihood over raw IQ,
   including fractional reslicing or a calibrated polyphase interpolator. The
   current prototype estimates relative delay from channel vectors after the
   integer slice; it does not iteratively reread fractionally shifted raw IQ.
3. Compare summed per-frame likelihood fitting against regression of frame
   maxima on weak frames.
4. Calibrate timing and process noise with known sample-clock offsets and
   omitted-RF refill simulations.
5. Repeat on untouched dwells with predeclared regions, rolled-pilot controls,
   and dual-receiver common-rate/free-offset fits.

Until those steps pass, standardize frame-local CFO and reset-safe robust rate;
persist phase and relative timing as diagnostics only.

## Artifacts

- `reports/figures/2026_08_25_frame_phase_rate_prototype/summary.json`
- `reports/figures/2026_08_25_frame_phase_rate_prototype/locklets.json`
- `reports/figures/2026_08_25_frame_phase_rate_prototype/frame-phase-rate-prototype.png`
- `reports/figures/2026_08_25_frame_phase_rate_prototype/artifact-manifest.json`
