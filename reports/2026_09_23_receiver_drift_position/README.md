# Receiver drift improves frequency fit but worsens position generalization

The receiver-drift model should **not be promoted**. A training-only selected
ridge improves reserved frequency residuals on both complete validation groups,
but geographic error worsens from 2.154 to 3.284 km and from 6.640 to 9.291 km.
Sub-300 m generalization remains unproven.

| Validation view | Zero-drift error | RX-drift error | Zero-drift reserved capped RMS | RX-drift reserved capped RMS |
|---|---:|---:|---:|---:|
| Sep 22 18Z, 10 scans | 2.154 km | 3.284 km | 250.61 Hz | 228.78 Hz |
| Its first scan | 2.241 km | 1.917 km | 184.12 Hz | 185.20 Hz |
| Sep 23 08Z, 12 scans | 6.640 km | 9.291 km | 272.09 Hz | 259.85 Hz |
| Its first scan | 7.861 km | 10.854 km | 300.80 Hz | 312.69 Hz |

The nested first scans are sensitivity views, not independent groups. The first
improves by 324 m while the second worsens by 2.992 km. The two complete groups
are consistent: better frequency prediction does not produce better position.

## Training-only selection and exact receiver support

The first twelve sessions in frozen TRAIN order select ridge 1000 s² from
`[0, 100, 1000, 10000]`. Their pooled inner-reserved RMS values are 381.583,
381.569, 380.524, and 384.599 Hz. The zero-drift shared-bracket context is
409.321 Hz over the same 4,841 complementary rows; it was computed separately
and was not an eligible hyperparameter arm. This shared-bracket result is not
comparable to the earlier roughly 197 Hz free ±5-second per-track timing model.

All 11,658 cached observations in those twelve scans reconstruct exactly through
public trajectory contracts. Seven scans contain both RX0 and RX1 selected
support and five contain RX1 only. Thus the earlier 840-observation all-RX1
example could not be generalized. Validation reconstruction also closes all
18,893 observations: fifteen scans are dual-RX and seven single-RX.

The model fits one scan-local linear slope for each reconstructed stream ID and
a separate constant offset for each track at one of 17 saved host-bracket timing
points. Exact receiver-path IDs remain in the mapping audit, but do not create
extra oscillator coefficients. The ridge penalty is applied once per RX slope.
Candidate, timing, offsets, slopes, and position use training frequency rows;
complementary rows are evaluated only after the inference JSON is hash-sealed.

The zero-drift implementation exactly reproduces the prior shared-bracket capped
control in all four views: coordinates and geographic errors are identical, and
reserved capped RMS differs by at most 2.4e-12 Hz. This establishes a common
baseline for the model delta. Validation inference took 346.2 seconds.

## Limits and protocol deviation

The fit alternates candidate choice and regularized least-squares RX slopes for
at most twelve iterations. It then uses a capped duration-weighted outer score
with the same once-per-RX penalty. This bounded two-stage heuristic is not an
exact global capped-loss optimizer, and no per-fit convergence diagnostic was
recorded.

Trajectory construction normalizes frequency to the canonical 11.2 GHz carrier.
The fitted slopes are therefore in normalized units and only approximate a
constant physical LNB Hz/s across channels with different actual RF. Exact path
metadata could support RF rescaling in a future predeclared experiment; it was
not added after seeing these outcomes. Receiver drift remains confounded with
orbit, identity, timing, and track-shape error.

The final ridge selection was sealed before any validation frequency fit or
score. However, exact validation RX mapping was reconstructed before a
training-objective implementation correction. This accessed validation source
metadata and trajectory support earlier than the protocol intended. The first
training result is preserved as `training_selection_superseded.json`; correcting
the capped duration timing objective retained ridge 1000 s². No validation
frequency outcome motivated that correction or the model. This deviation limits
the procedural claim even though it did not expose validation frequency scores.

Published TRAIN coordinates, validation seeds, and candidate pools remain
historically response-conditioned. The experiment does not establish blind
full-catalogue acquisition. The retrospective-test 23 scans and prospective
evidence were not accessed, and no deployment, RF collection, or persisted
contract change was made.

Artifacts include the [frozen protocol](PROTOCOL.md), exact TRAIN and validation
receiver mappings, [training selection](training_selection.json),
[sealed inference](inference.json), [post-seal results](results.json), and the
[TRAIN zero-drift context](training_zero_drift_control.json).
