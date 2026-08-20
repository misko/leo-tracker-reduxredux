# Parked Qin follow-up work

This file records the two Qin-paper recommendations intentionally deferred from
the current edge-selection and channel-coverage work. Neither item is required
to make the existing narrowband edge-pilot pipeline truthful for upper and
lower captures.

## Narrow-edge SSS synchronization

**Status:** Parked. Do not silently import or depend on `leo-tracker`; it remains
a numerical oracle only.

**Future scope:** Independently port and document the published Starlink SSS
sequence and the frequency-domain slice visible in a pilot-centered narrowband
capture. Add an optional SSS timing/CFO estimator behind a narrow analyzer port,
then compare its frame epoch and CFO against edge-pilot acquisition. Its output
must be separate evidence, not an implicit replacement for GLRT64 track
proposals.

**Prerequisites:** Establish the authoritative publication and licensing/source
provenance for the SSS constants. Confirm which SSS bins fall inside each upper
and lower 2.5 MHz capture and specify the FFT, CP, phase, and frequency-index
conventions without copying private implementation assumptions from a reference
repository.

**Tests and acceptance:**

- Golden sequence/index test against the authoritative source.
- Synthetic upper- and lower-edge tests spanning positive and negative CFO,
  fractional epoch, gain, phase, and AWGN.
- Wrong-edge and rolled/random-sequence negative controls.
- Frozen-corpus comparison of SSS epoch/CFO versus GLRT64 acquisition with
  explicit tolerances and no degradation of current edge-pilot detections.
- Component runtime benchmark and a test proving the optional method is skipped
  cleanly when the capture does not contain the required SSS bins.

## Qin supplementary QPSK template and T-codes

**Status:** Parked because the paper PDF does not contain the full reference
template or the 40 recovered T-code values; they are described as supplementary
material. Do not reconstruct guessed values from figures or commit inferred
scientific fixtures.

**Future scope:** After obtaining the authoritative supplementary package,
archive its provenance and hashes, represent the modal QPSK reference template
and every published 60-bit BPSK T-code as versioned scientific fixtures, and add
a detector for the documented 16-subcarrier circular shift per OFDM symbol. Keep
T-code evidence distinct from invariant edge-pilot evidence because Qin reports
that T-codes are variable and absent from many frames.

**Tests and acceptance:**

- Byte-for-byte fixture/hash verification against the supplementary release.
- Tests for all published codes, circular shifts, interruptions by non-QPSK
  symbols, and continuation after interruptions.
- Wrong-code, random-QPSK, and shuffled-symbol negative controls.
- Synthetic SNR sweeps plus frozen-corpus detection/false-alarm baselines.
- Processing-gain reproduction within a documented tolerance of Qin's reported
  low-entropy-element result, without claiming deterministic every-frame data.
- Explicit review approval before any golden scientific fixture changes.
