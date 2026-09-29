# Next evidence gate: cross-receiver track coherence

This is a proposed diagnostic, not a completed model or a claimed localization
improvement. Both frozen correlation arms are now complete; their matched
ablation does not establish reliable sub-km localization across all datasets.
Do not expand the beamwidth grid in response to exposed-reference
errors. The hard-cone comparison already showed that mere geometric support
does not guarantee a useful Doppler explanation.

The current position models eliminate a separate constant frequency for each
track and do not enforce that two receivers observed the same emitter. A possible
source of additional information is a longer, shared trajectory supported by both
receivers, with an explicit relative receiver-frequency nuisance. This requires
testing the relationship between tracks before fitting geographic coordinates.
Simply declaring matching satellite nominees to be the same physical signal
would reuse uncertain associations and could double-count detections.

## What has and has not been tested

The earlier [paired-state study](../2026_09_28_rx_paired_state_cv/README.md) tested
four-category receiver detection states and signed nominal geometry. It failed
its later predictive gate. That result is not an evaluation of stitching the
exported geolocation frequency tracks under a common receiver-frequency offset.
The [track-competition audit](../2026_09_28_rx_track_competition/README.md) also
warned that overlapping tracks do not establish physical satellite multiplicity
or identity, and found poor later frequency support in its frozen-prefix banks.

The current exports contain receiver IDs, RF/channel labels, visit indices,
timestamps, frequencies and training masks. The inspected DS9-004 export has
overlapping RX0/RX1 tracks on channel 1. Metadata overlap is only readiness
evidence: no cross-RX frequency agreement, shared identity, calibrated LO offset,
or useful stitching result has been measured in this follow-up.

## Proposed bounded sequence

1. Freeze a read-only census over the same 72 distinct scans. Count the nested
   four-scan sets only once. Use only same-scan, same-channel, same-RF RX0/RX1
   pairs. Match training observations by common visit and timestamp tolerance
   fixed before execution; retain unmatched observations and every candidate
   pair in the output. Verify that timestamps/visits admit a one-to-one mapping,
   rather than choosing whichever frequency observation matches best.
2. Measure whether one constant frequency difference predicts the paired
   measurements, and whether that difference transfers across independent
   tracks within a scan/channel. A free offset for each pair can conceal an
   emitter mismatch. Set minimum overlap and span, noise model, pairing rule,
   ambiguity margin and held scoring before inspecting agreement results.
   Report training-to-held transfer and time-shifted/wrong-pair controls on
   identical eligible observations. Preserve absent and ambiguous matches.
3. Only after the frequency-coherence gate, inspect overlap of retained satellite
   candidates using the correct snapshot catalogue identity mapping. Stored
   candidate indices are not NORAD IDs. Candidate agreement is secondary
   evidence and must not replace independent frequency validation.
4. A future joint model would keep one trajectory per shared-signal hypothesis,
   a common receiver offset where supported, and an explicit unmatched-track
   alternative. Compare it with the exact independent-track model at zero
   coupling. Normalize assignment alternatives, prevent duplicate use of an
   observation, and test held isolation and synthetic incorrect-pair rejection
   before any geographic fits.

Do not interpret time order as travel direction without a validated shared
identity and calibrated receiver geometry. Do not interpolate through long
gaps merely to manufacture a continuous arc. A failed coherence or transfer
gate should stop this direction before a new fitting campaign.

Use existing observation exports first: no new RF, waveform processing,
propagation or archive/provider reads are required for the census. Its exact
protocol, tests and inputs must be sealed before execution. This proposal
does not change any completed correlation result or claim the sub-km goal is met.
