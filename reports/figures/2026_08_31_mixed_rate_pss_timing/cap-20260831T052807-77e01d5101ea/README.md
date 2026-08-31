# Mixed-rate PSS frame-timing replay

Capture: `cap-20260831T052807-77e01d5101ea`

This is a development replay of the candidate-only, rate-generic PSS timing module. It is not a
Standard pipeline product and it does not claim decoded PSS/SSS, satellite identity, or absolute
carrier phase.

## Declared search

- Published 1056-sample PSS construction at 240 MS/s, independently projected into each recorded
  complex passband.
- Native channel reference: 1,325,117,187.5 Hz.
- Dense frame-epoch search at 0 Hz receiver-relative CFO, followed by candidate-only refinement on
  -400 to +400 kHz in 100 kHz steps.
- 750 Hz frame lattice; maximum eight separated modes; at least four frames.
- Qualification requires both peak/median >= 1.15 and robust z >= 6.0.
- Every persisted continuity gap is a hard boundary. No match, frame lattice, or timing estimate
  crosses missing IQ.

## Result

| Path | Usable IQ | Continuity | Qualified blocks | Qualified windows | Strongest evidence |
|---|---:|---:|---:|---:|---|
| 2.5 MS/s, stream-1 RX0 | 60.000 s | 1 segment, no gaps | 1 / 60 | 750 | 1.433x median, z=6.49 |
| 15 MS/s, stream-0 RX1 | 43.782 s | 233 segments, 16.218 s missing | 20 / 233 | 2,831 | 1.921x median, z=11.57 |

The 2.5 MS/s result is one isolated candidate in device time `[34, 35)` seconds, beginning near
2026-08-31 05:28:48.381 UTC. Its frame phase is 2,720 samples modulo 3,333.333 samples and the 750
local maxima have a 2.91-sample spread inside the declared +/-2 microsecond refinement window.
Because adjacent one-second blocks do not retain that epoch, this remains weak, isolated evidence.

The 15 MS/s result is materially more persistent. Two early segments at device times 16.50--16.92
seconds share a phase near 19,217 samples modulo 20,000. A later cluster recurs across segments
149--167 and again at 172, spanning device times 38.24--44.39 seconds (approximately
05:28:51.815--05:28:57.967 UTC). Segment-level epochs in the main cluster occupy 556--597 samples
modulo 20,000, a 41-sample (2.73 microsecond) span despite the intervening gaps. Most refinements
select the coarse -100 kHz CFO bin; isolated segments select 0 or -200 kHz.

This is credible evidence for a repeatable **PSS-like frame-timing lattice in the 15 MHz upper-edge
projection**, and is stronger frame-boundary evidence than this replay obtains from the 2.5 MHz
slice. It is not evidence that the upper-edge slice contains the full synchronization region: the
module matches only the band-limited PSS projection visible inside the recorded passband. SSS and
full-band identity remain unresolved. The coarse PSS CFO bins must not be substituted for the
known-pilot Doppler estimator.

The complete machine-readable replay, including every candidate and every qualified frame window,
is in `pss-frame-timing-replay.json` (SHA-256
`a4867e64a070744332b56158b2b69abde1982241f3b1179594c5625e28b656bd`).

## Figures

- `pss-detection-vs-time.png` plots the strongest folded timing hypothesis in every searched block,
  the robust-z qualification threshold, qualified detections, and continuity-safe IQ availability.
- `pss-frame-phase-vs-time.png` plots every locally refined frame window and each folded epoch in
  microseconds modulo the 1,333.3 microsecond frame period. Phase is relative to each receiver's
  device axis and must not be compared as absolute phase between radios.

## Verification

- New PSS module, replay-adapter, and figure-renderer tests: 19 passed.
- PSS tests plus existing Starlink template, blind acquisition, and seeded acquisition regressions:
  67 passed.
- Ruff and strict mypy checks pass for the new implementation and replay tool.
- An explicit SciPy numerical-oracle audit (not a runtime dependency) gives normalized-template
  coherence of 0.999986 at 2.5 MS/s and 0.999982 at 15 MS/s.
