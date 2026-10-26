# The two overlap examples enter at different detector stages

This is a readback of the preceding sealed synthetic outputs, not a new
detector experiment. The same highest-margin accepted candidate is retained;
no candidate is chosen using generated truth. Its final CFO equals acquired
CFO plus the fractional GLRT residual. All 28 signal-case receiver outputs
pass that arithmetic identity.

![Acquisition error and the additional GLRT step](stage_attribution.png)

In the same-epoch 3,000 Hz pair, the approximately −456 Hz final difference
comes mainly from **one −443.892 Hz GLRT residual step**; the acquired CFO is
only about −12 Hz from the stronger generated tone. In the 500 Hz pair, the
approximately +54 Hz displacement is already in acquisition and GLRT adds
zero. Isolated strong, separated-epoch and chirp examples also retain zero
GLRT residual for these highest-margin outputs.

The deployed `conditioned_glrt64_score` uses 64 consecutive pilot symbols
(indices 2 through 65) in each frame. Their nominal duration is about 0.282 ms.
It evaluates a 512-point frequency grid, spacing 443.892 Hz, then sums frame
powers. A 20 ms input therefore does not imply a coherent 20 ms frequency
estimate, and the zero-padded grid spacing is not the underlying spectral
resolving power. The archived 3,000 Hz result shows a specific refinement-bin
choice, not merely noisier acquisition. The saved decomposition locates the
change; it does not independently establish why that bin wins.

The chirp's midpoint difference is already present in acquisition. It cannot
be diagnosed as a GLRT-bin problem from these outputs. Its effective-time
convention still needs separate analysis before labeling the difference bias.

A useful diagnostic is to feed the same actually selected candidate identities
and timestamps to graph construction with final versus pre-refinement CFO.
That tests the stage's contribution without an extra detector invocation or
truth-based selection. It does not justify globally disabling GLRT refinement.
Similarly, previous 300-symbol remeasurement experiments already exist and
did not yield a qualified cohort gain; any new refinement should address this
specific overlap mechanism and include isolated-source controls.

All original limitations remain: a pilot-only model, a known template/grid
discretization mismatch, two fixed seeds, shared generated signals across the
two receiver noise streams, and no graph or geographic result in this readback.
This is not a field-bias or satellite-identity conclusion.

[All 28 stage decompositions](stage_attribution.csv),
[source hashes and numerical summary](summary.json), and
[saved-output reporter](readback.py) preserve the evidence. The historical
detector and scientific fixtures are unchanged.
