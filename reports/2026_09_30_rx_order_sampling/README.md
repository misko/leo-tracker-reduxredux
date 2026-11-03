# Receiver order sampling audit

The sole uncensored event in the earlier detection-order pilot has a recorded RX0-before-RX1 lag of **9.3431466 seconds**. That lag is larger than the immediately preceding eligible observation gaps. Sampling cadence alone therefore does not explain away this recorded order. However, sparse and ambiguous candidate hits do not establish physical beam entry or a shared satellite identity.

This audits the existing frozen endpoint rather than choosing a new event or relaxing a gate. The original population contains 180 hypothesis-period sequences. Only one supplies the retained lag, in a reused calibration recording's reception period; none supplies a lag in the final frequency-target period. The hypothesis is catalogue candidate 69338 in recording `scan-fw-3ebf3526172258af`. Its prior conditional top-three weight was already 1.0 to displayed precision.

| Measure | RX0 | RX1 |
|---|---:|---:|
| Gap from preceding eligible no-match opportunity to first unique hit | 0.2808732 s | 0.9422274 s |
| Unique hits from first hit onward | 10 | 12 |
| Ambiguous candidate opportunities from first hit onward | 3 | 15 |
| No matching candidate opportunities from first hit onward | 87 | 59 |
| Span from first to last unique hit | 33.9891740 s | 18.3690948 s |

Under the **unverified** assumptions of perfect detection and a single persistent onset, the preceding no-match and first-hit timestamps would bracket an RX1-minus-RX0 onset lag between **8.4009192 and 9.6240198 seconds**. This is a hypothetical bracket, not a confidence interval or a measured physical arrival lag. Frequency matching, missed detections, ambiguity, transmitter activity and incorrect candidate identity remain alternative explanations. The post-first-hit counts do not support treating all subsequent windows as continuously detected.

## Consequence for the next model

Keep recorded order as potentially useful evidence, but do not turn this single sampled lag into an east/west motion label or a hard geometric constraint. The next useful sequence model must preserve multiple candidate explanations and nondetections, allow changing target presence, and score future observations without a matching gate. A hard first-hit lag estimator currently lacks enough evaluation events.

Existing experiments also constrain that next step:

| Existing model | Evidence | Implication |
|---|---|---|
| Temporal derivative of receiver contrast | Held density −5.625 nats versus static geometry with correlated noise; 1/4 recordings improve | Do not repeat this derivative extension as a new order model |
| Geometry with explicit target absence | Combined static-minus-Doppler −0.066484 nats/window; tilt-minus-static −0.001483 | Presence assumptions materially change geometry conclusions |
| Geometry against causal frequency continuity | Later tilt-minus-static +0.019066 nats/window, positive in 5/6 records; tilt beats swap and reversal in 6/6 | Some incremental directional evidence survives stronger controls |
| Same causal-reference comparison | Full tilt beats the causal reference in only 2/6 later recordings | Incremental geometry gain still does not establish reliable satellite association |

These supplementary results qualify the earlier [progress summary](../2026_09_30_progress_summary/README.md): geometry evidence includes positive reception and controlled incremental effects, alongside weak absolute association support. None supplies a new location-error measurement.

## Evidence and verification

[audit.py](audit.py) streams the saved matched-opportunity rows, reproduces the frozen first-hit timestamps, excludes out-of-scope opportunities, preserves ambiguous statuses and computes support gaps and post-hit counts. [results.json](results.json) contains source hashes and exact outputs. Three component tests pass, checking missing opportunities, immutable endpoint matching and ambiguity preservation. The audit completes in under one second; no new RF, raw-IQ processing, location fit or source mutation occurs.

Sources: [order pilot](../2026_09_28_rx_receiver_order/README.md), [temporal contrast](../2026_09_28_rx_beam_crossing/REPORT.md), [target absence](../2026_09_28_rx_presence_geometry/README.md), [causal reference](../2026_09_28_rx_causal_geometry/README.md).
