# Standard five-state Kalman tracking

Standard receiver-path analysis publishes `standard.kalman-tracking` schema V1
after final CFO trajectory selection. This is an additive contract; no existing
persisted Standard schema or golden scientific fixture changes.

## Model

The implementation follows Equation (8) in Kozhaya, Saroufim, and Kassas,
“Unveiling Starlink for PNT,” *Navigation* 72(1), 2025 (DOI
`10.33012/navi.685`). Its state is

`[carrier phase, angular frequency, angular-frequency rate, frame phase, frame-rate error]`.

The carrier block uses constant angular-frequency rate, while the frame block
uses constant frame-rate error. Process noise enters angular-frequency rate and
frame-rate error. The implementation evaluates the paper's exact continuous
white-noise covariance integral for every elapsed interval, so missing/off frames
are handled by a longer prediction rather than by inventing measurements.

The default process and measurement tunings are the values reported in the
paper: carrier process PSD `(2π)^2 rad²/s³`, frame process PSD
`0.004² s²/s`, carrier-phase measurement sigma `2π×10⁻⁵ rad`, angular-frequency
measurement sigma `π×10⁻² rad/s`, and frame-phase measurement sigma
`3×10⁻⁷ s`. They are persisted in `KalmanTrackingConfigV1` and included in the
Standard configuration digest.

## Repository-specific measurement boundary

The paper correlates a blindly estimated full OFDM beacon. This repository's
truthful Standard boundary remains the known Qin edge synchronization pilots.
For every complete received frame belonging to a final trajectory, the analyzer:

1. wipes the final polynomial CFO phase from 64 known pilot symbols;
2. obtains prompt phase from their coherent complex correlation;
3. obtains a frame-local Doppler measurement from the weighted correlation-phase
   slope;
4. derives frame phase from the acquired frame epoch against the 750 Hz frame
   lattice; and
5. feeds phase, angular frequency, and frame phase to the five-state filter.

The product records open-loop innovations and closed-loop estimates for phase
shift, frame phase/rate, Doppler shift, and Doppler rate. It also flags phase slips
and abrupt CFO corrections from the pre-update innovations. Histories and track
counts are explicitly bounded and report omissions/truncation.

The product is candidate-only and known-pilots-only. It does not claim the full
OFDM beacon, decoded payload, satellite specificity, code phase, pseudorange, or
positioning.

## Pilot-phase ambiguity discovered after V1

Later verified-IQ work found that the Qin edge-pilot channel can occupy two
phase families separated by pi. Standard V1 wraps carrier phase over 2 pi and
therefore interprets many valid binary-family changes as resets. Its persisted
contract remains immutable and its products remain useful historical
diagnostics, but reset counts must not be read as physical carrier resets.

The Research-only
[pilot PNT Kalman](../../reports/2026_08_22_pilot_pnt_kalman.md) instead uses a
modulo-pi carrier measurement plus an explicit observed binary sign. It also
uses the phase ramp across eight tones as receiver-relative fractional timing.
That experiment does not replace Standard V1 and still does not recover the
paper's code phase or pseudorange.
