# Stable-LNB interpretation of the saved simultaneous double differences

This assessment applies the user's explicit assumption that each warmed-up LNB
has stable phase behavior. It does not establish that assumption from hardware
measurements. No new RF was collected or published analysis overwritten.

## What cancels

For a shared source s, model the RX1-minus-RX0 phase as

`D_s(t) = G_s(t) + C(t) - 2*pi*f_s(t)*tau + H_s(t)`.

G is geometric phase, C is common receiver/oscillator phase, tau is differential
group delay, and H represents remaining source-dependent channel phase. All
phases are wrapped unless continuity is independently established.

Simultaneous `D_B-D_A` cancels C even when C varies. Stable phase offsets are
therefore not themselves a barrier to geometric double differences. Under a
common channel response, or a justified bound on its differential contribution,
the result estimates `G_B-G_A`. It does not identify either absolute G alone.

For one source, temporal differencing cancels a constant C and constant H.
A stable nonzero oscillator frequency offset instead produces a phase ramp;
removing a ramp estimated from that same source can also remove geometric
slope. Such a procedure is not independent evidence for geometric slope.

## Quantitative delay sensitivity for the existing overlap evidence

Input: `figures/2026_09_21_adaptive_dual_rx_local_phase/scan-hop-28d7592ea614f624-signal-subband-v1.json`.
Verified file SHA-256:
`a690e1cb264039edfc242b384acb2a08bbff2f6ff9f65b0f85182d3bb63b1038`.
Use only its `source_overlap_evidence.blocks` with `both_sources_qualified=true`.
These are simultaneous 20 ms blocks; the older asynchronous pilot pair phase
is not substituted. The source separation comes from the stored alias-aware
frequency authority. Delay sensitivity is `360*abs(delta_f)*abs(tau)` degrees.
The stored evidence first removes a common phase nuisance estimated outside
the target bands. Equal window boundaries alone do not guarantee cancellation
after averaging if the two sources weight a changing common phase differently;
the direct uncertainty follow-up must check that sensitivity as well.

| Visit | Separation (Hz) | Qualified blocks | Circular mean DD (deg) | Circular residual RMS (deg) | Bias for 100 ns delay (deg) | Delay giving 5 deg bias (ns) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1065 | 35823.421 | 4 | 13.006 | 16.941 | 1.290 | 387.704 |
| 1109 | 34670.425 | 4 | 15.263 | 18.345 | 1.248 | 400.598 |
| 1136 | 33138.357 | 2 | 3.063 | 1.121 | 1.193 | 419.118 |

The means above are descriptive equal-weight circular means, not precision
estimates. The two-block scatter in visit 1136 must not be interpreted as a
1-degree measurement uncertainty. Existing time-bandwidth-based per-source
errors are optimistic (roughly 13–26 degrees); actual DD uncertainty also
depends on covariance, effective sample count, matching, and channel effects.

A 10 ns delay contributes only 0.119–0.129 degrees; a 1 microsecond delay
contributes 11.930–12.896 degrees. These are sensitivity scenarios, not measured
delay bounds. A zero integer-sample correlation peak does not establish a
subsample group-delay bound across all relevant signal paths.

For a fixed 100 ns delay, the change in its DD contribution between visits
1065 and 1136 is only 0.097 degrees. However, interpreting their measured DD
change as geometric evolution additionally requires verified source identity
across visits and stable source-dependent response. No slope is established
by these three descriptive means.

## Revised conclusion and next discriminating evidence

An external absolute phase calibration is not a prerequisite for every useful
geometric observable. Simultaneous close-frequency double differences can be
reported as conditional geometric estimates with explicit channel assumptions
and delay sensitivity. The earlier blanket calibration blocker was too broad.

The current 10 qualified blocks support measuring this conditional observable,
but do not establish a resolved geometric trend or satellite catalogue identity.
STL geometry constrains mounting surfaces; it is not evidence for source
association, electrical phase-center location, or antenna phase response.

The next useful work is to estimate uncertainty of simultaneous DD directly
from matched block IQ, preserving shared receiver noise covariance and checking
independent time/symbol subsets. A stable-delay nuisance term should be bounded
or jointly assessed rather than requiring absolute phase calibration up front.
Any claim of recovered geometric evolution must exceed that uncertainty and
survive those controls. Absolute phase for either satellite remains a distinct,
unresolved quantity.
