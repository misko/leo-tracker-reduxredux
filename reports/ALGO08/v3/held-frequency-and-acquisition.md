# Where a shorter recording analysis loses evidence

The all-visit 20/8 ms receiver and compact solver remain the research comparison. Across the North and South simulations they used 21.294 s from original I/Q through publication and exit, versus 30.503 s for installed ALGO08v3. That leaves **6.04 s** to remove from the pair. The paired median time fraction was 0.700 and the summed fraction was 0.698. A complete physical withhold reached 2.79×. A representative physical panel with both timing fractions at or below 0.500, preserved fix rate and preserved location accuracy remains open. [Complete paired results and physical-position interventions](physical-transfer-and-raw-time.md)

## Which satellite did the unseen frequency support?

On dense DS30-0008, switching the satellite assignment on 222 identical observations moved the fixed-zero and fitted-calibration errors by 337 and 341 metres. To check the choice, we removed one frequency from both radios **before** constructing tracks, nominating satellites or fitting nuisance parameters. Forecasts from seven frequencies were sealed before evaluation on the eighth. We repeated the procedure on DS30-0057, recorded 21 hours later, with its own independently nominated rivals. Both recordings come from the same physical site. [Controlled position comparison](dense-family-refit.md) · [Training and nomination](dense-family-holdout.md) · [Forecasts, calibration and absolute scores](dense-family-holdout-offline.md)

![Cumulative held-frequency evidence for each recording's first satellite versus its second](development/held-frequency-choice.png)

Positive values favor the first satellite in each title. Each increment is the difference in log predictive score over one ten-second interval on the held frequency. The graph uses separate vertical scales. Repeated measurements on one trajectory provide correlated evidence. Removing a block below holds both training forecasts fixed and drops only its contribution to the held score. These are sensitivity checks on the same recording. [Figure and deletion calculation](held_interval_sensitivity.py)

| Recording and calibration | First minus second, all held data (nats) | Weakest result after removing 10 s | Weakest after removing 30 s | First satellite versus clutter, all held data |
|---|---:|---:|---:|---:|
| DS30-0008, zero | +19.04 | +11.31 | **−2.12** | +660.54 |
| DS30-0008, fitted | +1.53 | **−0.93** | **−4.25** | +687.27 |
| DS30-0057, zero | +122.15 | +60.63 | +6.13 | **−47.36** |
| DS30-0057, fitted | +116.96 | +56.81 | +3.42 | **−50.14** |

On DS30-0008, dropping the 180–210 s interval reverses both calibration arms. Dropping just one ten-second bin reverses the fitted result in two of 30 possible starts. RX2 also favors the other satellite in both calibrations. On DS30-0057 the relative order survives every tested deletion, yet **both satellites predict the held frequency worse than the pure-clutter model**. That distinction matters for a fast solver considering whether to discard a rival. This experiment produced no independent transmitter identity or new position. Cold preparation plus first scoring cost 15.12 and 5.88 CPU s. The dense repair we sought to avoid cost 0.738 CPU s. [Held observations and cost](dense-family-holdout-offline.md) · [Original dense repair](dense-8ms-prefix.md)

A second prototype scored the joint Doppler residual across multiple tracks after removing allowed receiver drift. Once given the candidate states, it needed about 2 ms per dense pair. It reproduced the signed objective's preference for the **less accurate** dense assignment and its preferred branch on the South 100 m omission that published a false fix. Both results include fixed-zero and fitted calibration. The experiment skipped zero discovery passes. A faster evaluation of those two states offers no measured saving in generating them. [Fixed-state replay, aborted-run costs and reference checks](curvature-projector.md)

## What paid for acquisition and regional checks

| Experiment | Measured result | Decision |
|---|---|---|
| Four-frame ordinary receiver, preserving full two-scan anchors | 6.6444 ms is the shortest tested window supporting all four frame origins. It retained 41/61 signed 8 ms factors on a DS30-0008 member and 35/45 on DS30-0169, losing seven and four strong factors. Native short search saved 5.5–8.6 CPU ms, while all four complete worker pairs took longer through exit. | Retain 8 ms. Both independent physical signal checks failed before a position trial. [Signed factors and timings](four-frame-primary.md) |
| Original 20/8 ms acquisition on DS30-0169 | In **296.9 CPU ms**, the detector used 127.6, decoding 77.6, decoded hashes 23.8, compressed hash/framing 17.5, descriptor and transfer 36.0, and all other work 14.4. The native detector already borrowed views of the decoded windows. | Any input saving must address transfer or decoding/authentication while charging all original bytes. Eliminating a conversion at the native handoff offers negligible time. [Reader attribution and supply of already-decoded samples](ingress-eight-audit.md) |
| Bound the unfinished exterior likelihood, retaining exact fallback | On dense, the bound reduced 3,050 receiver-1 track evaluations to 1,490. Geometry had already been computed, and CPU rose from 699 to 767 ms against the current implementation. Medium and South near saved 24 and 13 ms. South far withheld correctly and added 15 ms. | Keep the existing regional implementation as the timing reference. A lazy projection would have to avoid unique orbit-time evaluations before taking credit for them. [Regional scopes and four actual decisions](regional-decision-bound.md) |

The missing full physical positive comparison still requires access to a complete authenticated recording. DS30-0016's former NVMe path resolves to the busy bulk volume. Its stopped stage still lacks 891,159,550 bytes. Across eight exact physical recordings with 92–808 scheduled visits, zero of 804,172 payload pages and zero of 1,815 index pages were resident. Twelve previously used staging and derived-output directories contained no complete matching recording. The check opened no waveform bodies. [Source custody](remote-custody-0016.md) · [Physical enrollment and exact extents](next-resident-8ms.md)
