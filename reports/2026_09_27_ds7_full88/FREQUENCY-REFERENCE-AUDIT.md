# DS7 frequency-reference semantics audit

## Finding

The existing Wave 3 unit audit remains correct about the implemented pipeline: persisted native tracking CFO is dealiased and multiplied by `11.2 GHz / actual_rf_hz` before the baseline exporter emits `measured_hz`. This review narrows the meaning of the denominator. In the installed scanner path, `actual_rf_hz` is the **actual hardware tuning center expressed at RF**, not the published edge-pilot carrier and not a measured carrier frequency.

The detector does account for the coarse offset between the tuner center and the published pilot center before estimating CFO. It constructs a nominal pilot baseband center from `pilot_if_center - tuned_center`, searches residual CFO around that center, and publishes `tracking_cfo_hz = acquired_cfo_hz + residual_cfo_hz`. The trajectory layer then scales that complete baseband-coordinate value by `11.2 GHz / tuner_center_rf_hz` and profiles a free stationary offset per track downstream.

This establishes a small, concrete reference distinction: Doppler of a pilot is physically proportional to the pilot carrier, while the implemented normalization denominator is the tuner center. It does **not** establish that this distinction causes the position error or authorize changing the model. The edge-pilot/tuner separation is only hundreds of kilohertz on an approximately 11 GHz carrier, and the free per-track stationary offsets absorb constant baseband-center terms. A matched, reference-free sensitivity and held-prediction gate would be required before treating the distinction as material.

## Exact trace

1. The channel contract defines the published edge-pilot RF centers. Channel spacing is 250 MHz; the first lower and upper pilot centers are 10,709,687,500 and 10,940,312,500 Hz ([`starlink_frequency.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/contracts/starlink_frequency.py:7>), [`starlink_edge_rf_center_frequency_hz`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/contracts/starlink_frequency.py:15>)).
2. Scanner targets are built at the maximum-coverage **tuning** center, which clamps the pilot center so the full receiver passband remains inside the 240 MHz channel. `ScanTarget.rf_center_hz` is set to that tuning center plus the LNB LO, while `if_center_hz` is the corresponding tuner IF ([`starlink_maximum_coverage_if_center_frequency_hz`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/contracts/starlink_frequency.py:51>), [`scheduled_low_band_targets`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/scanner/models.py:164>)).
3. Capture evidence binds `actual_lo_frequency_hz + actual_if_offset_hz == target.if_center_hz`; `actual_if_offset_hz` is restricted to ±10 Hz ([`AdaptiveHopEventV1`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/scanner/adaptive_hop.py:185>)). The legacy projection explicitly computes `actual_rf_hz = target.rf_center_hz - actual_if_offset_hz` ([`persistent_hop_trajectory.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/application/persistent_hop_trajectory.py:225>)). The current public tracking projection carries the already materialized `probe.actual_rf_hz` unchanged ([`scanner_trajectory.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/application/scanner_trajectory.py:95>)). Thus the name means the attested tuner RF center after its tiny tuning offset; it is not a measurement of the received pilot carrier.
4. Before detection, the scanner independently computes the published pilot IF center and subtracts the actual LO/tuned center to obtain `nominal_baseband_hz` ([`adaptive_hop_analysis.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/scanner/adaptive_hop_analysis.py:632>)). The search geometry records `tuned_center_frequency_hz`, `pilot_if_center_frequency_hz`, and `nominal_pilot_baseband_hz`, then constructs a `ReceiverFrequencyCalibration` whose center is that nominal baseband offset ([`pilot_search_geometry.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/analysis/starlink/pilot_search_geometry.py:140>), [`ReceiverFrequencyCalibration`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/analysis/starlink/acquisition.py:44>)). This is geometry-bound centering, not an independent oscillator calibration.
5. Acquisition returns an absolute baseband-coordinate CFO from calibration center plus searched residual. GLRT refinement adds its residual again when producing `tracking_cfo_hz` ([`pilot_methods._score`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/analysis/starlink/pilot_methods.py:995>)). The adaptive product copies the detector's fractional tracking CFO without changing units ([`adaptive_hop_analysis.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/scanner/adaptive_hop_analysis.py:532>)), and the public trajectory projection copies it to `measured_cfo_hz` verbatim ([`scanner_trajectory.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/application/scanner_trajectory.py:107>)).
6. Trajectory reconstruction groups candidates by `(channel, edge, receiver, actual_rf_hz)`, computes `scale = canonical_rf_hz / actual_rf_hz`, scales both the complete measured CFO and the alias spacing, and subtracts the chosen scaled alias ([`persistent_hop_trajectory._lane_tracklets`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/analysis/persistent_hop_trajectory.py:384>)). Preparation copies the graph's resulting `measured_cfo_hz` into `AdaptiveTrackInput.measured` ([`adaptive_tle_position_inputs.py`](</opt/leo-tracker/current-api/.venv/lib/python3.14/site-packages/leo/operations/adaptive_tle_position_inputs.py:114>)). The DS7 exporter copies that numeric array as `measured_hz` and separately labels the denominator as track `rf_hz` ([`ds7_export_baseline.py`](../../tools/ds7_export_baseline.py:65)).

The resulting implemented formula is therefore:

```text
pilot_rf_hz = published edge-pilot RF center
tuner_rf_hz = target.rf_center_hz - actual_if_offset_hz
nominal_pilot_baseband_hz = pilot_rf_hz - tuner_rf_hz
native_tracking_cfo_hz = nominal_pilot_baseband_hz
                         + acquired residual
                         + GLRT refinement residual
exported_measured_hz = (11.2 GHz / tuner_rf_hz)
                       * (native_tracking_cfo_hz
                          - relative_alias_index * 227272.727... Hz)
```

The first three detector terms are schematic names for the code path, not a claim that hardware errors can be uniquely decomposed after measurement.

## Concrete metadata evidence

The frozen Wave 3 examples use `actual_rf_hz = 11,440,000,000 Hz` for channel 3. The published channel-3 upper edge-pilot center from the contract is `11,440,312,500 Hz`, while the 10 MHz maximum-coverage tuner center is clamped to `11,440,000,000 Hz`. Their 312,500 Hz difference exactly matches the distinction above. The six cached visit 5/8/11 examples reproduce the implemented tuner-denominator formula within `1.1e-10 Hz` ([Wave 3 audit](../2026_09_27_ds7_wave3/frequency-units/audit.json), [interpretation](../2026_09_27_ds7_wave3/frequency-units/README.md)).

The relative denominator difference in that example is about `2.73e-5`. It scales a 100 kHz value by about 2.7 Hz. This order calculation bounds the direct numerical distinction for that lane; it is not an estimate of position impact. The stationary per-track offset can absorb a constant shift, but it cannot in general absorb a time-varying Doppler-scale difference.

## Evidence against a large omitted coarse-offset correction

- The tuner-to-pilot offset is already included in detector acquisition geometry before CFO is persisted; it is not silently omitted.
- The detector publishes the acquired absolute baseband coordinate plus its GLRT refinement residual, rather than only a small residual around zero.
- Relative CFO aliases are scaled in the same domain as the measurement before subtraction.
- Six concrete cached values close the implemented formula to numerical precision.
- A free stationary offset is profiled for every baseline track, absorbing constant frequency-reference offsets within a track.

These points argue against a missing hundreds-of-kilohertz additive correction. They do not prove that tuner RF is the ideal multiplicative Doppler reference.

## Evidence for a remaining reference ambiguity

- The field used as normalization denominator is derived from the hardware tuning center, while the tracked waveform is an edge-pilot band with a separately defined carrier center.
- The `ReceiverFrequencyCalibration` used here is synthesized from tuning/pilot geometry. It does not contain a measured per-receiver, LNB, or oscillator calibration.
- The capture contract attests the requested/actual digital tuning relation to ±10 Hz, but does not establish the physical LNB LO or receiver frequency accuracy at the same level.
- The code scales the full absolute baseband-coordinate CFO, including its nominal tuner-to-pilot offset, rather than first separating a physical carrier-referenced Doppler term. Track offsets reduce the consequence of that choice but do not define its physical semantics.

## Explicit unknowns

1. The reviewed schemas do not state whether Doppler normalization was intentionally defined at tuner center for numerical convenience or intended to approximate the pilot carrier.
2. The persisted data do not independently identify received pilot carrier frequency, transmitter offset, LNB LO error, receiver oscillator error, and orbital Doppler. Only their combined baseband CFO is observed.
3. There is no hardware-path calibration in this scanner evidence that establishes the physical RF scale per receiver or capture epoch.
4. This audit does not quantify position sensitivity to substituting pilot carrier for tuner center. Doing so would be a new, predeclared matched model experiment with exact masks, banks, offsets, and held prediction; it cannot be inferred from geographic scores.
5. The result may differ by edge, channel, and capture bandwidth because maximum-coverage tuning clamps relative to the selected pilot. Any future audit must derive the denominator per frozen visit rather than apply one global 312.5 kHz adjustment.

## Source binding and decision

The installed sources match the Wave 3 hashes for trajectory reconstruction (`1951ba2c...`), scanner projection (`844f23c0...`), adaptive preparation (`2b2c68c...`), adaptive analysis (`ce99c7fa...`), and pilot methods (`c33de1f8...`). Additional reviewed hashes are: application trajectory projection `05d769be...`, pilot search geometry `9263029b...`, Starlink frequency contract `835a26af...`, scanner models `fe3d886b...`, and adaptive-hop event contract `e3663daa...`.

Decision: the current 11.2 GHz normalization is reproducible and internally consistent with its declared `actual_rf_hz` field, but that field is specifically a tuner-center reference. There is code-level evidence of a small pilot-carrier versus tuner-center multiplicative distinction. There is no evidence here that it is large enough to explain the full-88 outcome, and this diagnostic does not authorize a correction, refit, or score comparison.
