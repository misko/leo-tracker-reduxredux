# Exact-Qin polynomial-phase injection into frozen POST-FIX hard-null backgrounds

Date: 2026-08-25 UTC

Status: **protocol frozen before the first IQ read; no results in this commit**

This preregistration defines a bounded component experiment for measuring
Doppler-rate estimator bias against known truth in real recorded noise. The
machine-readable authority is
[`polynomial-phase-injection-protocol-v1.json`](../config/analysis/polynomial-phase-injection-protocol-v1.json).
It is subordinate to the deny-by-default
[`doppler-experiment-dataset-policy-v1.json`](../config/analysis/doppler-experiment-dataset-policy-v1.json)
and uses only its `polynomial_injection` role.

The spans, scenarios, estimator settings, metrics, and gates were selected from
committed metadata and sealed manifest fields. No IQ bytes or response metrics
were opened while making these choices.

## Frozen real backgrounds

All three inputs are published POST-FIX, counter-authoritative, capture-wide
four-path hard nulls. Each selection is a two-second `stream-0` / 5d4d / RX1
span wholly contained by one digest-pinned CI16 chunk.

| Capture | Sample interval | Time interval | Chunk |
|---|---:|---:|---:|
| `cap-20260825T062228-886fe2dd9cde` | `[20,000,000, 25,000,000)` | 8–10 s | 1 |
| `cap-20260825T105640-facdadeffb3b` | `[55,000,000, 60,000,000)` | 22–24 s | 3 |
| `cap-20260825T111222-a2d4ce2afb9a` | `[90,000,000, 95,000,000)` | 36–38 s | 5 |

The staggered offsets give early, middle, and later capture positions without
examining signal response. Exact recording-manifest, Standard-analysis-manifest,
compressed-chunk, and uncompressed-chunk digests are frozen. Dynamic discovery,
substitution, active-background injection, and all holdout/new captures are
forbidden.

## Exact signal and frame geometry

The primary waveform is the repository's exact lower-edge, pilot-only Qin
template returned by
`leo.analysis.starlink.templates.qin_edge_pilot_frame(2_500_000, "lower")`.
It contains 3,333 `complex64` samples and the published 300-by-8 Qin edge-pilot
symbols. Its frozen digest is
`15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657`.
That digest is produced by the public `template_sha256` helper: the array is
serialized as canonical little-endian interleaved complex64 bytes. It is not a
hash of a temporary complex128 conversion.

Frame start `k` is `round(10000*k/3)`, giving only 3,333- and 3,334-sample
intervals. One complete 3,333-sample template is added at every occupied start.
It therefore never overlaps the next frame; a 3,334-sample interval retains one
untouched background sample. The two-second span contains 1,500 opportunities.
Occupancy is an exact-count deterministic subset produced by a separate frozen
PCG64 seed stream.

Physical CFO is the derivative of integrated polynomial phase about the
one-second reference epoch:

\[
f(u)=f_0+r u+\tfrac{1}{2}a u^2+\tfrac{1}{6}j u^3,
\]

where `u = (receiver_time - 1 s)/(1 + clock_ppm*1e-6)`. This makes
receiver-clock truth and injected physical truth separately computable. A
physical CFO step at 1.1 s and a known 750 Hz alias-label change at 1.0 s are
separate factors.

## Frozen fractional design

The experiment contains 18 explicit rows. It is not a full factorial. Every
factor is marginally balanced, and all 18 SNR/occupancy/clock triples are
distinct.

| Factor | Frozen levels | Count per level |
|---|---|---:|
| Real background | three exact captures | 6 |
| Rate (Hz/s) | -6,000, -3,500, -1,500, +1,500, +3,500, +6,000 | 3 |
| Acceleration (Hz/s²) | -800, 0, +800 | 6 |
| Jerk (Hz/s³) | -300, 0, +300 | 6 |
| Raw occupied-frame SNR (dB) | -32, -24, -16 | 6 |
| Frame occupancy | 0.35, 0.65, 1.00 | 6 |
| Known alias-label change (Hz) | -750, 0, +750 | 6 |
| Physical CFO step (Hz) | -300, 0, +300 | 6 |
| Sample-clock scale (ppm) | -25, 0, +25 | 6 |

Every row has a unique frozen seed. SNR is injected occupied-frame mean power
divided by the measured mean power of the entire frozen background span.

## Production-aligned frame CFO and fixed histories

Timing is supplied and the receiver-coordinate frame-reference CFO is rounded
to its nearest 750 Hz bin before fine estimation. This deliberately conditions
the experiment on a correct coarse acquisition/alias basin; it does not use the
fine truth as the frame-CFO result.

The primary measurement is the public
`evaluate_edge_pilot_frame_cfo_likelihood` kernel with its embedded split
validation. The even fold alone decides training support and supplies each CFO
point. Its 17-symbol-rolled control is the public estimator's frozen
pilot-specificity gate. Odd exact and odd rolled-control profiles remain held
out and cannot select a frame, history, or parameter. Frozen gates are ±2 kHz
residual support, even exact coherence at least 0.02, and nonnegative even
exact-minus-control margin. Profile evidence uses a 50 Hz grid.

The downstream 20 ms, 125 ms, and 500 ms fits call the public
`track_adaptive_frame_cfo` implementation with one fixed history at a time,
the existing 50 Hz measurement scale, 95% history coverage, 100 ms reset gap,
and its existing robust-line settings. Thus the primary comparison qualifies
the same frame-CFO and fixed-history estimator family used by the recent
studies; there is no custom-QPSK or custom-periodogram primary lane.

An offline full-span cubic is a diagnostic for rate, acceleration, and jerk. It
uses weighted least squares with the same fixed 50 Hz frame scale and inflates
covariance by residual reduced chi-square when greater than one. It does not
replace any causal candidate.

## Metrics and decision

Every output row retains training support, even estimate, odd response,
even/odd exact and rolled-control likelihood evidence, estimate uncertainty,
and error in two coordinates:

1. receiver-clock truth, the primary estimator-calibration coordinate; and
2. injected physical truth, exposing the separate sample-clock contribution.

Bias, RMSE, median absolute error, failure rate, and nominal 95% interval
coverage are reported by estimator and by background, SNR, occupancy, clock,
alias, and step strata. The 500 ms after a physical CFO step is excluded from
smooth-rate calibration and retained in a separate recovery analysis.

The preregistered promotion subset is smooth/no-step, SNR at least -24 dB, with
all three backgrounds represented. The fixed-500-ms candidate must have rate
RMSE at most 250 Hz/s, absolute-error failure rate at most 10%, and nominal 95%
coverage between 80% and 99%. The diagnostic cubic must have acceleration and
jerk RMSE no greater than 250 Hz/s² and 250 Hz/s³, respectively.

## Interpretation boundary

This is a truthful component calibration, not an end-to-end acquisition test.
Timing and the correct coarse 750 Hz basin are supplied. The waveform is exact
Qin pilot content but contains no unknown payload. The alias event is known and
does not test blind alias detection. The backgrounds are real POST-FIX receiver
noise but hard nulls, not active-signal interference. Results can calibrate
frame-CFO and fixed-history rate error conditional on the supplied acquisition
basin; they cannot establish full acquisition yield.
