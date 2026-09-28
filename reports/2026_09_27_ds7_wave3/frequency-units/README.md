# DS7 frequency units audit

The persisted `TrackingCandidate.fractional_tracking_cfo_hz` is native physical
receiver CFO in Hz. The detector constructs it as acquired CFO plus residual
CFO, and the scanner persistence and public projection copy it verbatim. No
`11.2 GHz / actual RF` normalization occurs at those stages.

The baseline exporter does not ultimately preserve that projected value
verbatim. `prepare_adaptive_tle_position_inputs` first reconstructs persistent
hop trajectories. That analyzer scales the candidate CFO and its alias spacing
by `canonical_rf_hz / actual_rf_hz`, selects a relative alias index, and writes
the normalized, dealiased value into the physical episode graph. Preparation
then copies the graph observation into `AdaptiveTrackInput.measured_hz`.

The exact relationship is:

```text
native = fractional_tracking_cfo_hz
native_alias_spacing = 1 / 4.4 us = 227272.72727272726 Hz
exported_measured_hz = (11.2 GHz / actual_rf_hz)
                       * (native - relative_alias_index * native_alias_spacing)
```

Six cached candidates from visits 5, 8, and 11 at 11.44 GHz reproduce the
baseline export within `1.1e-10 Hz`. Receiver 0 uses relative alias index 0;
receiver 1 uses index 3. The concrete values are recorded in `audit.json`.

Thus both statements require their scope:

- Cached `fractional_tracking_cfo_hz` is native physical Hz and must not be
  called canonical 11.2 GHz CFO.
- Baseline exported `measured_hz` is normalized to the declared 11.2 GHz
  reference and dealiased by the trajectory-relative alias convention.

The solver's fixed 11.2 GHz prediction is therefore dimensionally matched to
the prepared track values. It is an inherited model convention backed by an
explicit upstream trajectory normalization, rather than a reinterpretation of
the raw persisted candidate.

Installed source SHA-256 values:

- `analysis/persistent_hop_trajectory.py`: `1951ba2c0843c7e23a94390257d611fa255dc5251f3c5bfde487ba2069ea80a8`
- `application/scanner_trajectory.py`: `844f23c068af8c6f6a0477f1a0ce2997e1066b2585d4cbca24781f62ab8c3e7b`
- `operations/adaptive_tle_position_inputs.py`: `2b2c68c2eab3bd26d60c9d366fa6b1dc8cc580b3b7b77ca549f8cf2383fdd477`
- `analysis/starlink/pilot_methods.py`: `c33de1f8ed7b3d8f1f1b7de659d6aa2b110f658338eb2753ae2c5161757a2857`
- `scanner/adaptive_hop_analysis.py`: `ce99c7fa3f22a432e32572e4b24ab6601ceba402815f1fc4a1cafe034d8d96f1`

No IQ, pose, reference score, or new RF was accessed. Two pure mapping tests
cover the cached examples and the expected scaling of a synthetic 1 kHz native
frequency shift.
