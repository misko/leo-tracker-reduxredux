# Lag-3 proposal controls

This directory contains a frozen, synthetic, proposal-only challenge set for the
lag-3 phase kernel. It does not contain detector outcomes, thresholds, or a
claim that an injected pilot must pass a detector. `design.json` fixed the case
membership, seeds, trajectories, rates, edges, and interpretation before IQ was
materialized.

The builder uses the repository's published Qin edge-pilot generator. Physical
frame starts lie on `epoch + k * sample_rate / 750`; it applies the varying
sub-sample shift at every frame rather than accumulating rounded frame starts.
CFO and tones use absolute source-counter phase and reduce the large initial
phase in extended precision before producing samples. Arrays are CI16 with
shape `(sample_count, 2, 2)` in sample, receiver, I/Q order.

Run:

```bash
.venv/bin/python reports/2026_09_27_ds5_cached_tracking/lag3_controls/build_controls.py
.venv/bin/python -m pytest -q reports/2026_09_27_ds5_cached_tracking/lag3_controls/test_controls.py
```

The raw arrays are ignored by Git and can be reproduced only while
`source_lock.json` matches the design, builder, and pilot-template source.
Consumers should evaluate raw lag-3 complex phase/magnitude and proposal CFO
before GLRT. For `ambiguity=single`, association uses the declared 2 us circular
timing and 8 kHz CFO gates. `ambiguity=either` accepts either injected pilot.
`ambiguity=invalid` supplies no required pilot identity. A negative/noise
proposal is not a detector false positive unless a separately declared detector
and GLRT decision rule says so.

These inputs omit unknown data/QAM subcarriers and frequency-selective or
time-varying channels. They test proposal sensitivity to timing, CFO, noise,
tones, and ambiguous mixtures; they do not establish full downlink fidelity.
