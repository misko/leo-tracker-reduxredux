# Phase connection prerequisites for the recent longest track

## Evidence from the recording

The immutable raw manifest for `scan-hop-6adcb067e2dbce43` records a device-counter timebase at 2,500,000 samples/s. This is stronger evidence for relative timing than host wall-clock timestamps. The first-sample UTC bracket is 1,291,650 ns wide, but that common absolute epoch uncertainty must not be assigned independently to every dwell.

| Visit | Valid start device counter | Channel / edge | Fastlock slot |
|---:|---:|---|---:|
| 1354 | 448652301001 | 3 / lower | 2 |
| 1394 | 448665078487 | 3 / lower | 2 |
| 1428 | 448675877956 | 3 / lower | 2 |
| 1713 | 448766537043 | 3 / lower | 2 |

The first-to-last valid-start difference is exactly 114,236,042 counter samples, or 45.6944168 nominal seconds. The previous report's 45.694244352-second span used the tracking candidates' centers, not the phase fits' centers. Counter continuity provides a coordinate for connecting phase. It does not establish that receiver differential phase remains continuous through retunes, or that the differential LNB frequency is known accurately enough across gaps.

## Corrected phase time axis

The original binding tool assigned each phase the average tracking-candidate UTC timestamp. The phase fit can use a different local window inside the same dwell. Research schema v2 now retains the tracking timestamp as association evidence but calculates relative phase time from each visit's integer device start counter plus the actual phase fit's local fractional center. Large counters are subtracted as integers before any floating-point arithmetic.

Rebinding the existing 20 phase results changes the first-to-last fit-center span to **45.7492334166 seconds**, with gaps of **1.73046–5.12524 seconds**. The maximum relative-time correction is **94.91 ms**. The complex phase estimates themselves are unchanged; this correction does not resolve their integer cycles or receiver terms. The 45.713-second RF trajectory overlap remains a separate inventory quantity.

- [Corrected timing JSON](figures/2026_09_21_recent6ad_phase_time_v2/phase-time-v2.json), canonical digest `sha256:f75313def33788e86ad959f3d14e504fd1b0a2294040bcc49ed569bec7bd5886`.
- [Corrected timing PNG](figures/2026_09_21_recent6ad_phase_time_v2/phase-time-v2.png).
- Regression test uses counters above `2**58` and deliberately different tracking and phase centers; it verifies the fractional local-time difference survives without large-counter rounding. All three binding-tool tests pass.

## Why stable frequency is not constant phase

The independently measured RX1-minus-RX0 frequency offset is approximately -675.5 kHz. A stable nonzero frequency difference gives continuously rotating phase. For a shared source, a useful measurement model is

`measured_phase(t) = geometric_phase(t) + receiver_phase(t) + estimation_error(t) (mod 2π)`.

If the receiver phase is known constant after suitable frequency correction, its unknown intercept cancels from a temporal single difference. This is a valid conditional route to geometric phase changes. The saved data do not currently validate the correction across dwell gaps. A constant receiver frequency is also confounded with a locally linear geometric phase trend when estimated only from this one source.

For a 5-degree phase budget, the allowed average frequency error over a gap is `5 / (360 * gap_seconds)`. The selected gaps of 1.77–5.11 seconds require approximately 0.0078–0.0027 Hz precision in that average, including changes during unobserved intervals. The measured per-visit train/held-out frequency differences have median magnitude 32.55 Hz and maximum 84.02 Hz. Those differences are not a calibrated uncertainty on the gap integral, but they do not supply the millihertz-level evidence needed to connect cycles under this budget. Fitting an apparently smooth wrapped curve cannot supply that evidence independently.

At 675.5 kHz, one 2.5-MS/s sample corresponds to about 97.3 degrees of phase. Any future propagation must use exact integer device-counter differences plus local fractional support offsets, rather than subtracting large UTC nanosecond values after conversion to floating point. Accurate counters make this calculation possible; they do not remove oscillator or estimator errors.

## Estimator audit before physical interpretation

The existing `coherent_pilot_frames` estimator separately estimates a residual frequency for each receiver, then rotates the selected pilot symbols to their frame origin. This estimates an intercept outside the centers of the symbol windows. When residual-frequency fits differ between windows or receivers, the extrapolated phase can differ even if the underlying relative phase is stable. High coherence across frames does not independently bound that intercept bias.

The large contiguous-half disagreements in the longest-track report therefore remain **estimator-repeatability failures**, not proof of physical receiver instability or non-geometric satellite motion. The completed [bounded shared-residual audit](2026_09_21_shared_residual_phase_half_audit.md) demonstrates frame/symbol alias mistakes in the historical half-window fits. An opt-in shared-residual estimator reduces disagreements from 113.18 to -4.67 degrees and from 123.08 to -20.11 degrees, all compared at exactly the same sample time. Residual disagreement and sensitivity to imperfect frequency authority remain; neither a geometric phase trajectory nor a total uncertainty is established. Published evidence is retained unchanged; no phase alias is selected by making the result resemble an expected orbit.

## Provenance

- Raw authority: `/srv/bulk/leo/scanner-adaptive-recordings/scan-hop-6adcb067e2dbce43/manifest.json`, inspected read-only.
- [Track-bound phase results and immutable input digests](2026_09_21_scan_hop_6ad_long_track_phase.md).
- Estimator: `src/leo/analysis/starlink/adaptive_dual_rx_phase.py`, `coherent_pilot_frames`; phase extraction: `src/leo/analysis/starlink/adaptive_dual_rx_phase_extract.py`.

This audit identifies remaining prerequisites; it does not claim recovered geometric phase.
