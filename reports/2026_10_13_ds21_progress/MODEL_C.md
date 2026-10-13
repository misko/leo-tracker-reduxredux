# Model C: joint native association

Status: implemented; five-recording shared-proposal development comparison
complete. This is an interim report; the full DS21 0.5 km target is unmet.

The model fits position and calibration while marginalizing satellite identity,
native measured frequency branches and clutter. Physical Doppler uses each
observation's RF. These fast scans have zero validated temporal edges and neutral
waveform weights, so this comparison measures per-window joint association,
not confirmed satellite tracking.

| Development recording | CH1–4 km | CH5–8 km | CH1–8 km |
| --- | ---: | ---: | ---: |
| DS21-001 | 5.791 | 3.293 | 1.425 |
| DS21-003 | 3.839 | 0.850 | 1.957 |
| DS21-005 | 0.644 | 3.714 | 1.556 |
| DS21-023 | 4.579 | 5.058 | 4.899 |
| DS21-039 | 3.759 | 2.557 | 4.291 |

All results use fitted `c`. CH1–8 median is 1.957 km and maximum 4.899 km;
0/5 are below 0.5 km or 1 km. Half-band runs inherit all-training ambiguity
initialization, so they are not fully independent band-only pipelines.

Preserving all native within-cell candidates later improved DS21-005 to
0.909 km but worsened DS21-023 to 5.149 km; that mixed control was not promoted.
Its half-band comparisons have not been rerun, so it cannot be used to claim an
isolated improvement from combining bands. Weak receiver-pair coupling also
worsened the matched position comparisons despite improved convergence.

The completed DS21-039 diagnostic crosses full/half-band geometry and satellite
timing with full/half-band physical calibration on identical native observation
support. It reports satellite, ambiguity-cell and sampling-integer posteriors,
visibility and clutter. A separate coordinator diagnostic uses the same window
likelihoods to assess observation weighting and block concentration. Full/half
states change satellite-or-clutter assignments in 18–20% of windows. No RF-scaling
error was found; calibration, timing and association interact.

An additional 18 fixed-position profiles and seven warm/free continuations on
DS21-039 exposed a missed optimizer basin. The unchanged all-band objective
improved from 33,172.423 to 32,380.955, but post-seal position error improved only
from **4.291 to 4.073 km**. This is a separate development control with extra
search effort, not a replacement for the matched five-case table above. It
remains worse than the historical high-only result and does not meet 0.5 km.
The [refinement report](../2026_10_13_ds21_039_root_cause/REFINEMENT_RESULTS.md)
retains all outcomes. The subsequent three weighting controls gave 4.314, 4.106
and 4.592 km; the winner-preserving native-candidate prior gave 4.410 km against
the matched 4.073 km baseline. All sixteen new fits were stationary. None of
these changes is promoted; better frequency fit again failed to improve accuracy.

Four matched receiver RF fits then added one opposite-sign receiver slope while
keeping common `c` fitted. All were stationary. The selected contrast was
17.471 Hz/GHz, but position error worsened from 4.073 to 4.085 km despite a small
objective improvement; this is also not promoted. A separate zero-optimizer
block-residual audit found persistent receiver/band structure with unstable
cross-products and nearly unsupported channel tails. It does not establish a
stable shared-noise covariance or a hardware clock fault.

See the [common progress report](README.md) for evaluation coverage, reference
limitations and the plan for full DS21. No locked evaluation result is claimed.
