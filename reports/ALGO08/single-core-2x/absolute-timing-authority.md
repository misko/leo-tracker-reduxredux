# Absolute receive timing and stereo authority at the public boundaries

The released ALGO08v2 inputs provide relative pilot timing and Doppler. Absolute range would require a link between each repeated frame and its transmit epoch. The public generator draws that phase independently per transmitter, and both simulated lanes share one station position. On the physical DS30-0016 input the saved clock authority is a host bracket around a receive counter. Capture-bound electrical baseline and phase calibration belong to a separate adaptive phase product. None of these inputs supplies an independent absolute range or angle for a transferable 100 m membership decision. [Prespecified check](absolute-timing-protocol.md) · [Measured receipt](measurements/absolute-timing-authority.json)

## What the timing fields contain

| Input stage | Available authority | Consequence for range |
|---|---|---|
| Public waveform | The generator uses retarded path delay at one ECEF receiver location, an independently drawn 750 Hz frame phase for each emitter, shared sample rate and clock offset, and a 0.42-sample shift on RX1. Each lane and window draws its own carrier phase. | The two lanes contain the same geometric propagation delay. Their relative arrival contains the synthetic lane delay and estimation error. |
| Public recording | The writer stores simultaneous dual-lane samples at nominal 10 MS/s in 20 ms windows. The first receive counter has a 10 ms host-style UTC bracket. The emitter phases and physical ADC clock parameters are latent generator settings. | Timing binds the receive schedule and relative counters. Inter-satellite differencing leaves the independent transmitter phase difference. |
| Saved physical input | The DS30-0016 native file has a 178.041601 ms receive bracket, host monotonic and realtime delivery stamps, and a null source timing field. Its candidate fields contain the integer and fractional pilot offset, CFO and verification scores. | Delivery stamps bound when samples were received. The pilot fields carry neither a transmit epoch nor calibrated inter-lane phase or group delay. |

[Public IQ generator](../../../tools/pipeline_eval/qualification/waveform_site_model.py#L57) · [Public recording writer](../regional-release/blind_panel.py#L92) · [Physical receive bracket convention](../../../src/leo/acquisition/continuous_window_ppu.py#L121) · [ALGO08 acquisition and native export](../../../tools/algo08_scan.py#L32) · [Native factor fields](../../../src/leo/contracts/scanner_tracking.py#L73)

Each 10 MS/s sample represents 100 ns. The nominal frame period is (1/750) s, or 13,333⅓ samples. The decoder adds the fractional offset to the integer pilot position and reduces the difference of hardware counters on this rational lattice. The generator also adjusts the received period for sample-rate error and radial motion. The periodic code has a one-frame range ambiguity of about 399.7 km even if its transmitter phase is known modulo the frame. A TLE element epoch timestamps the orbit elements. The waveform phase is drawn separately from that epoch. [Counter-to-phase arithmetic](../../../tools/pipeline_eval/qualification/range_epoch_model.py#L18) · [Generator arrival, received period and lane offset](../../../tools/pipeline_eval/qualification/waveform_site_model.py#L114) · [Hardware timing metadata](../../../src/leo/contracts/radio.py#L141)

## Constant range is absorbed by the transmitter phase

Let τₛ(t) be the propagation delay for transmitter s, φₛ its unknown transmit phase in seconds, and β the receiver clock offset. The observed repeated-code timing depends on τₛ(t) + φₛ − β, modulo the period and with lane delay added. Adding a constant to the path delay and subtracting it from the transmit phase preserves the emitted-frame index calculation and received sample epoch on both lanes. This holds even with the receive clock fixed. A constant delay leaves the received period unchanged. Taking a difference between transmitters removes the common receive offset and leaves φₛ − φⱼ, so a common nominal cadence alone supplies no independent inter-satellite range.

At both public sites the causal orbit calculation uses the previously locked positions A and B, 200 m apart across the midpoint face, and the same held owner support. At each emitter's first paired epoch, choosing the alternate phase absorbs the entire instantaneous A-to-B delay change. Across both sites every equality held within 9.54 × 10⁻⁷ samples, the numerical scale of the calculation. The whole trajectory retains the subsequent time variation in the A-to-B path difference. This is the part accessible to relative arrival tracking. The table reports full-arc variation before a clock-rate fit. It measures a different quantity from the previously held short-interval discrimination. [Per-satellite reparameterization and field inventory](measurements/absolute-timing-authority.json) · [Earlier held code increments](mirrored-arrival.md)

| Public site | Paired epochs / satellites | Raw A-to-B delay RMS / maximum, samples | After removing each first-epoch difference, RMS samples | Measured RX1−RX0 median, samples | RMS about the generated +0.42 samples |
|---|---:|---:|---:|---:|---:|
| North | 224 / 12 | 2.687 / 5.687 | 1.133 | 0.440 | 0.103 |
| South | 208 / 13 | 3.691 / 6.155 | 0.688 | 0.445 | 0.101 |

The simulator's co-located receivers give exactly zero stereo path difference for any position. The observed 44–45 ns offset traces the lane timing instead. The test removes an independently free intercept per transmitter, so it provides the same structural result in the fixed-zero and fitted RF calibration gauges. No frequency fit or region decision was changed. The earlier held geographic preference from the remaining arrival variation failed to transfer between the mirrored offers. [Physical code–carrier sign control](arrival-observability.md) · [Conditional Doppler and orbit noise experiment](mirrored-noise.md)

## What would make the extra observations identifiable

A verified frame number and transmit UTC, or calibrated relative epochs across enough identified transmitters, would constrain the free transmit phases. A ranging solution would also need to resolve the frame ambiguity and account for receiver clock and RF-chain delays. Clock-only calibration improves the reception time and leaves the independent transmit phases free.

The separate adaptive phase schema can bind fixture pose, phase-center refinement, chain calibration and independently verified direction evidence to a capture. Its reconstruction checks those authorities and their validity intervals. The ALGO08v2 native documents inventoried here carry none of those bindings. An earlier physical fixture had nominal 80 mm mount separation with unverified RF phase centers and cable mapping. For scale, an 80 mm calibrated baseline at 500 km slant range and fixed world orientation would have at most about 32 µm of first-order differential path change for a 200 m translation, or 0.11 ps. This calculation is illustrative. Recovering direction would require capture-bound phase centers, pose and lane calibration, stable complex phase and ambiguity control. More than one independent direction constraint is needed for a geographic solution. [Adaptive geometry input](../../../src/leo/scanner/adaptive_dual_rx_geometry_input_v1.py#L139) · [Calibration checks](../../../src/leo/application/adaptive_dual_rx_geometry_v2.py#L97) · [Prior physical fixture and timing audit](../../2026_09_21_dual_lnb_phase_toa_feasibility.md)

## Reproduce

The saved-data runner validates the published native detections, the earlier frequency-only associations and stereo pairing, and the exact causal catalogue snapshots. It does not read the planted receiver, transmitter phases or later generator orbit. The physical control reads only the saved timing fields. Nine component tests passed, including an authority-positive control where fixing the transmit phase exposes a known 500 ns path change.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
north=("$bench"/covariance-north-inside/baseline/fast-scan-automatic-work/*/detections.json)
south=("$bench"/covariance-south-inside/baseline/fast-scan-automatic-work/*/detections.json)
physical=("$bench"/physical-endpoint-paired/DS30-0016/baseline/fast-scan-automatic-work/*/detections.json)
archive=/tmp/leo-regional-qZJKBw4W/public/tle
flock "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH="$PWD:$release/src:$release" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.single-core-2x.absolute_timing_trial \
  "${north[0]}" "${south[0]}" "$archive" "$release/assets/tracks.json" --physical "${physical[0]}"
```

[Runner](absolute_timing_trial.py) · [Gauge and authority-positive tests](../../../tests/pipeline_eval/test_absolute_timing_trial.py)
