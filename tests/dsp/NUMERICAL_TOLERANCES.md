# Detector parity numerical tolerances

These tests preserve numerical behavior; they do not establish a calibrated
Starlink detection threshold.

The frozen values were generated from the unmodified numerical oracles at
`leo-tracker` commit `0bb80d14759fd8496b74e7d3219a690be18565a6`
(`src/leo_tracker/radio/beacon/pilots.py`, `acquisition.py`, and `decode.py`)
and checked against `leo-tracker-redux` commit
`b2b8827832715f7cd45196cd08919bcc5dd2a3f0`
(`starlink_templates.py`, `starlink_acquisition.py`, and
`starlink_pilot_constellation.py`). The new implementation does not import
either source tree at runtime.

- Qin waveform samples use absolute complex error `1e-7`, matching complex64
  rounding. Canonical complex64 payload digests must match exactly.
- Deterministic synthetic acquisition requires exact epoch recovery, CFO within
  `1 Hz`, and frozen scalar scores within `1e-10`.
- The protected RETRO acquisition allows `35 Hz` CFO error. This covers the
  native multi-basin quadratic refinement's historical `16--30 Hz` difference
  from the older conditioned 100 Hz grid while still detecting basin drift.
- Hard-symbol accuracy allows one decision out of 2,400 (`1/2400`).
- Protected RETRO RMS EVM uses absolute tolerance `2e-6`, covering NumPy
  float32/float64 accumulation differences without hiding a symbol-scale change.
- Synthetic receiver weights use `1e-12` because all inputs and reductions are
  deterministic on the supported NumPy implementation.

RETRO is a consensus-proxy known-pilot candidate and remains candidate-only.
J1 is `PLANNED` because its full IQ object and frozen calibration are missing;
no test silently skips or reports J1 as passing.
