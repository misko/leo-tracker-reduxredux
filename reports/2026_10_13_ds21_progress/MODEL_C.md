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

The current assigned investigation crosses full/half-band geometry and satellite
timing with full/half-band physical calibration on identical native observation
support. It reports satellite, ambiguity-cell and sampling-integer posteriors,
visibility and clutter. A separate coordinator diagnostic uses the same window
likelihoods to assess observation weighting and block concentration.

See the [common progress report](README.md) for evaluation coverage, reference
limitations and the plan for full DS21. No locked evaluation result is claimed.
