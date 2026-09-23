# Relaxed adaptive phase gate ladder

This is a metadata-only, phase-blind expansion plan for
`scan-hop-28d7592ea614f624`. It separates a useful weaker single-source
coherence measurement from the much stronger requirement needed for a
two-source double difference. The frozen input is
[`relaxed-rx0-anchor-binding.json`](figures/2026_09_23_scan_glrt_multiplicity/relaxed-rx0-anchor-binding.json),
generated without opening IQ by
[`bind_adaptive_relaxed_phase_300s.py`](../tools/research/bind_adaptive_relaxed_phase_300s.py).

| Phase-blind level | Visits | RX0 source anchors | Permitted conclusion |
|---|---:|---:|---|
| Both receivers have one passed fractional candidate | 301 | 331 alias-deduplicated anchors | Per-anchor cross-RX pilot coherence can be measured after a training-only receiver-offset estimate. |
| Existing timing/offset-consistent one-source match | 258 | 263 matched records | The same measurement also has archived RX timing agreement. |
| Existing two-source match | 5 | 10 matched sources | A near-simultaneous source B-minus-A double difference is available. |

The relaxed binding includes all 301 first-level visits. Each anchor comes
solely from RX0 candidates that passed the persisted fractional-margin gate;
within RX0, candidates closer than 5 kHz after folding the 227.27 kHz symbol
alias are deduplicated. Later replay may apply the RX0 epoch to both receiver
streams and estimate the RX1-minus-RX0 carrier offset on seeded random training
frames. It must retain every anchor and report failures, rather than choosing
anchors after seeing coherence or phase.

This changes the measurement question. A relaxed anchor is not an independently
matched RX1 source and does not supply a two-source DD. Its value is to measure
whether a known RX0 pilot template coheres at RX1 under the shared-epoch,
training-calibrated receiver model, with exact-template, symbol-roll, and
wrong-timing controls scored on held frame groups. Compare its held coherence
and controls to the existing five strict rows, not its absolute wrapped phase
across retunes.

There are 30 relaxed visits with two or more distinct RX0 anchors: six on
channel 2, one on channel 3, and 23 on channel 4. The four additional
channel-4 candidates that initially appeared nearest to the strict five are
1023, 1045, 1117, and 1124. Each has one strict source, but its second RX0
anchor has nearest-RX1 timing residuals of 87.54, 1239.24, 1503.95, and 262.87
samples, respectively; their nearest tracking offsets also differ materially
from the approximately -676 kHz first-source offset. Relaxing the nine-sample
timing gate merely to include them would assert a source correspondence the
published metadata does not support. They belong only in the relaxed
single-source coherence cohort.

RX0 anchoring is asymmetric: within the same 301 visits, RX1 offers 362
deduplicated anchors and 60 multi-anchor visits, including 51 whose RX0 side is
not multi-anchor. A reciprocal RX1-anchor arm would be a useful bounded,
predeclared sensitivity analysis if the RX0-anchored replay produces positive
coherence. It should use the identical 5 kHz alias rule, seeded whole-frame
holdouts, fixed controls, and report both directions together. Do not combine
the arms or choose whichever gives a prettier phase trace.

No level provides satellite identity, cross-retune phase continuity, a resolved
750 Hz/227.27 kHz branch, or geometric position evidence. The archived GLRT
metadata came from the one 20 ms probe at the start of each 120 ms dwell; held
frames test the conditional replay calibration, not independent acquisition.
