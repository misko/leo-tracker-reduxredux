# Held full-anchor scores for whole-recording route selection

The frozen score chose the history route on North and South and the unfiltered route on DS30-0016 and DS30-0057. The selected archived positions clear the **named-v3 error plus 250 m** limit in both calibration arms on all four containing cases. North’s chosen history route cut fixed-arm error from **390 to 128 m**. On South, the same score preferred history even though history increased errors by **124 m fixed and 273 m fitted** versus unfiltered. That contradiction stops broader saved publication work in this study. [Frozen rule](anchor-cycle-route-protocol.md) · [Complete score and archive receipt](measurements/anchor-cycle-route.json.gz)

## Detection score

The detector already takes one full 20 ms stereo measurement every eight admitted visits for each RF, channel and edge. For score construction, every held anchor’s candidates were erased on both radios before carrier history replay. The empty opportunities remained in chronological order. The seven other visits of each complete original same-stream cycle give `n = 7` and a measured positive count `k` on each radio. The prediction `(k + 0.5) / 8` uses the unfiltered or recomputed history count. The outcome is whether the original full receiver verified a candidate. History wins the recording only if its held Bernoulli log score is strictly higher on each radio. Ties, disagreements and a recording with no complete cycles choose unfiltered. [Selector](anchor_cycle_route.py) · [Shared erasure and history code](anchor_holds.py)

| Recording | Complete cycles per radio | Held positives, radios 0 / 1 | History gain, radios 0 / 1 (nats) | Mean Brier, unfiltered → history | Selected route | Selected overhead CPU (ms) |
|---|---:|---:|---:|---:|---|---:|
| North | 144 | 39 / 39 | +28.366 / +26.345 | 0.1635 → 0.0846 | History | 16.10 |
| DS30-0016 | 85 | 43 / 27 | −15.273 / −8.948 | 0.1857 → 0.2307 | Unfiltered | 6.10 |
| South | 144 | 33 / 33 | +12.510 / +12.521 | 0.0769 → 0.0482 | History | 14.04 |
| DS30-0057 | 284 | 144 / 139 | −29.002 / −43.663 | 0.2120 → 0.2542 | Unfiltered | 24.22 |

Each recording dropped eight incomplete cycles per radio. The two paired block bootstraps resample the same 128- or 256-issued-visit blocks for both radios, with 2,000 draws at each width. The draw fraction favoring history on both radios was **99.05%/96.50%** on North and **99.95%/100%** on South. It was zero at both widths on each physical recording. North radio 1’s 256-visit mean-gain interval still spans zero at **−0.027 to +0.393 nats per anchor**. These intervals describe within-recording variability under only 3 to 21 original blocks, with no independent site-level replication. The receipt includes individual outcomes, prediction digests and reliability by donor count. [Paired calibration evidence](measurements/anchor-cycle-route.json.gz)

## Archived positions and decisions

| Containing offer | Named v3 fixed / fitted error (m) | Unfiltered fixed / fitted error (m) | History fixed / fitted error (m) | Selected fixed / fitted RF RMS (Hz) | Named v3 / unfiltered / history owners per arm |
|---|---:|---:|---:|---:|---:|
| North | 106 / 141 | 390 / 121 | **128 / 113** | 6.881 / 6.764 | 302 / 347 / 304 |
| DS30-0016 | 1,644 / 1,661 | **1,311 / 1,694** | 2,473 / 2,542 | 121.526 / 120.291 | 109 / 116 / 107 |
| South | 817 / 1,101 | 454 / 515 | **577 / 787** | 7.983 / 7.930 | 266 / 468 / 266 |
| DS30-0057 | 426 / 525 | **240 / 297** | 378 / 641 | 125.298 / 125.311 | 1,593 / 1,542 / 1,220 |

For each case the restored history packet matches the archived execution input or its sealed projection digest. The archive readback matches original offers and both-arm terminal coordinates, and verifies an identical owner digest across arms within each of the twelve containing publications. It verifies each complete terminal against its manifest with eight archived figures. For **both North and South**, named v3 and the two short routes all returned false fixes on the original **100 m omissions** and all withheld on the **52.5 km omissions** with null coordinates in both arms. A single acquisition-wide decision gives the same route for the containing and omitted offers. [Archived position and owner readback](anchor_cycle_publications.py) · [Exact coordinates and omitted decisions](measurements/anchor-cycle-route.json.gz)

## Runtime boundary and integration

Call `select_route(document)` from `anchor_cycle_route.py` and consume its `route` field. The default entry uses the original signed qualified 20/12 ms roster and the existing carrier-continuation implementation. It imports no solver or archive modules, uses no bootstrap, and does one erased history pass. If it selects history, apply `north_factor_swap.continued(document)` once to the unchanged original input before the single normal downstream solve. That original history rule sees the real anchor measurements and may reject some. The North and South overhead figures include that restoration replay. Selector CPU alone was **9.16, 6.10, 7.79 and 24.22 ms** in table order. These are single saved-input measurements with the attached diagnostic and reference I/O outside the clocks. [Callable API](anchor_cycle_route.py) · [Receiver-first and exact-rule tests](../../../tests/pipeline_eval/test_anchor_cycle_route.py)

The paired scores measure how well short detections predict a larger-aperture gate at its fixed schedule phase. History training deliberately lacks anchors while the selected inference route restores them. Neither those positives nor better RF RMS measures positional contribution, as South demonstrates. The dense archive had no verified complete history-only comparator and was excluded. No fresh positions, figures, waveform reads or end-to-end timings were produced here. Ten focused tests passed.
