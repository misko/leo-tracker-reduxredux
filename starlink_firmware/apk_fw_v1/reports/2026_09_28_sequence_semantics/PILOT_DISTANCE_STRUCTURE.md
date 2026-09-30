# Soft pilot-adjacent structure across cached DS7–DS9 visits

The changing early signal reproduces between receivers without forcing soft
symbols into bits. There is no consistent decline in reproducibility with
distance from the pilots over the observed range. However, the per-coordinate
reliability pattern does not reliably transfer between visits. This supports
retaining soft evidence and visit-specific uncertainty, not a universal mask
of reliable header positions. No additional packet field has been decoded.

![Pilot distance and reliability-profile transfer](local/pilot_distance_structure.png)

## Scope and frozen selection

This uses the existing nine DS7/DS8 paired caches and two DS9 paired caches,
with the same discovery/evaluation frames as `local_header_recovery.json`.
Input hashes are checked before analysis. Five caches have no eligible paired
frames under the existing held-pilot coherence gate and remain excluded:
S06, S07, S18, S19, and DS9-first. This is not an exhaustive corpus survey.

Actual native FFT bins align receivers; OFDM symbols 2–7 are examined. RX0
discovery frames alone select coordinates with 20–80% nonnegative real signs.
Unlike the previous hard-sign assay, no confidence threshold discards any
evaluation sample at a selected coordinate. Each complex sample is normalized
by its magnitude, preserving its continuous phase rather than hard slicing.
This deliberately removes amplitude from the present assay; the original
complex values remain in the input caches.

For each coordinate, both receivers' phase observations are centered over
evaluation frames. The complex metric is the real part of their normalized
inner product. Separate real-axis and imaginary-axis Pearson correlations
are also retained. Centering removes agreement caused only by a constant
coordinate mean. Scores are averaged equally across selected coordinates;
they are neither transmitter BER nor per-frame confidence probabilities.

## Within-visit results

| Visit | Coordinates | Complex correlation | Real-axis correlation | Imaginary-axis correlation | Largest mismatched-frame complex correlation |
| --- | ---: | ---: | ---: | ---: | ---: |
| S01 | 41 | 0.205 | 0.431 | −0.131 | 0.046 |
| S02 | 45 | 0.269 | 0.481 | −0.036 | 0.072 |
| S13 | 129 | 0.154 | 0.325 | −0.067 | 0.021 |
| S22 | 113 | 0.294 | 0.479 | −0.011 | 0.041 |
| S23 | 103 | 0.279 | 0.446 | 0.031 | 0.014 |
| DS9-middle | 95 | 0.466 | 0.627 | 0.183 | 0.016 |

Every visit's matched complex and real-axis correlations exceed all its
nonzero circular frame-shift controls. These shifts preserve coordinates but
misalign RX1 frames. They are descriptive controls, not independent trials.
After centering, the mean of all nonzero-shift correlations is mathematically
the negative matched correlation divided by the number of other frames.
Consequently that mean is **not independent corroboration**; the table uses
the largest shifted score instead, and the output also retains 95th percentiles.

The real component is consistently the stronger shared component. DS9-middle
also has positive imaginary correlation of 0.183, versus a largest shifted
imaginary score of 0.048. This early-symbol result does not prove a quadrature
data channel. Shared interference, phase/calibration errors, and other signal
components remain possible; the negative imaginary correlations in several
other visits emphasize that the residual does not have a universal behavior.

## Distance from pilots

Distance is measured in native FFT bins to the nearest actual pilot bin listed
by the decoder. Pilot groups are checked to agree between receivers. Positions
are grouped at distances 1–2, 3–4, 5–8, and 9–12 bins. Different groups contain
different coordinates, so a line in the figure is not a controlled intervention
on distance alone. S01/S02 cover only the nearer groups.

A supplementary distance correlation subtracts the mean within each OFDM
symbol and side of the pilot group, avoiding a slope driven solely by a
difference between symbols or pilot sides:

| Visit | Within-symbol/side distance correlation |
| --- | ---: |
| S01 | +0.164 |
| S02 | −0.070 |
| S13 | +0.070 |
| S22 | −0.012 |
| S23 | −0.010 |
| DS9-middle | +0.120 |

There is no consistent negative gradient in this sample. In DS9-middle the
grouped complex score is 0.412 at distances 1–2 and 0.491 at distances 9–12.
This does not rule out calibration error or deterioration outside the recorded
slice, and no uncertainty interval or causal effect is claimed.

## Transfer between visits

Visits are not synchronized transmissions, so their raw message symbols cannot
be compared frame by frame. Instead, the assay compares a source visit's
**discovery reliability profile** with a target visit's **evaluation reliability
profile**, using identical symbol/bin coordinates that are variable in both
discovery sets. At least 12 common coordinates are required.

Twenty directed comparisons among S01, S02, S13, S22 and S23 are available,
with 30–106 common coordinates each. Profile correlations range from −0.344
to +0.326. None exceeds the 95th percentile of 100 target-profile permutations
within each OFDM symbol. This is a descriptive diagnostic, not a calibrated
multiple-testing result; it does not preserve spatial correlation. It provides
no evidence that the precise reliability ranking generalizes across visits.

DS9-middle covers the other pilot edge and has no qualifying same-coordinate
peer in this cache subset. Its blank heatmap row/column means **unavailable**,
not zero correlation or failed transfer. We must not mirror upper/lower-edge
bins and treat them as identical protocol positions without evidence.

## Consequences and reproducibility

The observations support a shared changing early signal, including away from
the immediately adjacent pilot bins. They do not establish unencrypted data,
codewords, satellite identity or field boundaries. A future coding experiment
should retain soft observations and receiver-specific uncertainty, and should
not reuse one visit's quality ranking as a fixed mask for all visits.

`pilot_distance_structure.py` saves all coordinate metrics, frame splits,
source hashes, distance groups and transfer controls to ignored
`local/pilot_distance_structure.json`; it generates the figure above. The two
synthetic tests verify shared-varying versus mismatched observations, undefined
constant-coordinate behavior, and amplitude invariance. Both tests and Ruff
pass. All recordings were already on disk; no RF collection or download was
performed. Numerical outputs and the figure remain excluded from Git.

These recordings have been examined previously. The split is held out for
this fitting procedure, not a pristine project-wide holdout. Shared distortions
can affect both receivers. An independently validated coding rule is still
required before calling these soft observations decoded message bits.
