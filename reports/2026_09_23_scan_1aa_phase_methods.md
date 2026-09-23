# Phase tracking on scan-fw-1aa1d50103d97388

The strongest saved-IQ examples support a varying **RX1 − RX0 residual phase**
within each 120 ms dwell. A frequency-held-out broadband tracker establishes
support; an A-selected smoothing spline describes its evolution; shared-residual
pilot estimates agree with frame-matched broadband estimates after a training-only
offset. These measurements do not yet establish calibrated geometric phase or
continuous phase across retunes.

This is the pre-rotation 300-second, 2.5 MS/s scan beginning at
2026-09-23 14:30:28.399 UTC. The existing pipeline supports 26 of its 64 selected
dwells. Our bounded replay selected two dwells per RF channel by paired detection
strength before examining phase. Three of those eight dwells passed the existing
support rule; four failed it and one abstained for insufficient frequency support.
The figures below deliberately show the three supported examples. The
[full review](figures/2026_09_23_scan_1aa_phase_methods/REVIEW.md) includes all eight,
failures, method definitions, provenance, controls, and limitations.

## Broadband phase tracker

Blue uses frequency band A to track phase; orange checks it on disjoint band B.
Gray marks the first 60 ms used to estimate carrier and spectral response. Every
panel is a separate dwell, with its own phase reference. The phase wraps at ±180°.

![Broadband phase versus time](figures/2026_09_23_scan_1aa_phase_methods/best-broadband-phase-vs-time.png)

## Smooth phase estimate

The A-only model selection chose `spline_1` for all completed replay dwells.
For these supported examples, its later B-band RMS discrepancies are 20.8°, 16.1°,
and 26.9°, versus 123.7°, 43.4°, and 50.9° for linear fits. The spline uses A data
throughout the dwell: it is an offline estimate, not a first-half forecast.

![Spline phase versus time](figures/2026_09_23_scan_1aa_phase_methods/best-spline-phase-vs-time.png)

## Shared-residual pilot estimates

The two shared-residual variants agree well with the scalar phase evaluated at
their actual pilot frames. Offset calibration uses only first-half probes. The
refined variant is not uniformly better: visit 544 changes from 3.7° to 4.4° later
RMS discrepancy. Visit 2138 has only one training and one later estimate.

The pilot/scalar reference differs from the A/B reference above. The estimates
share IQ and carrier authority, so their agreement is an internal consistency
check, not independent proof of a satellite identity or geometric accuracy.

![Pilot phase versus time](figures/2026_09_23_scan_1aa_phase_methods/best-pilot-phase-vs-time.png)

## Reproduction and validation

The [full review and evidence bundle](figures/2026_09_23_scan_1aa_phase_methods/REVIEW.md)
records the scan binding, method sources, numerical outputs and all comparisons.
The [phase/time renderer](figures/2026_09_23_scan_1aa_phase_methods/render_best_phase_time.py)
uses only adjacent frozen JSON and NumPy/Matplotlib. No new RF was collected.
Twenty existing numerical tests passed; five overlapping replay results matched
production evidence exactly and six refined-pilot RMS values matched to 0.0001°.
The new phase/time figures were rendered and visually inspected.
