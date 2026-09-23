# Local differential phase is not predictively stable in the 28.2 s example

The prespecified development condition fails. On 100 seeded-random held physical
groups, the exact-template double-difference phase has 1.300 rad held RMS after
a training-only affine fit and residual resultant 0.462, below the required
0.8. The exact model is more coherent than the rolled-symbol and swapped-epoch
controls, but that relative result does not make its phase predictively stable.
The 0.462 resultant is a conditional descriptive concentration, not a calibrated
significance statistic.

This reuses the stream-1 28.200 s, 20 ms development snippet. The
[protocol](2026_09_23_local_differential_phase_protocol.md), implementation, and
tests were frozen at `83e94359`; sealed input hashes were committed at
`701c8e1c` before IQ was opened. Seed 20260929 is the original probe-4 split,
and the replay verified both train and held sample-index hashes against the
frozen joint-pilot result. The one read-only replay completed in 1.54 seconds.

| Model | Held affine RMS (rad) | Held residual resultant | Held constant RMS (rad) | Minimum projection coherence |
| --- | ---: | ---: | ---: | ---: |
| Exact | 1.300 | 0.462 | 1.067 | 0.030 |
| Rolled symbols | 1.728 | 0.067 | 1.808 | 0.006 |
| Swapped epochs | 1.830 | 0.014 | 1.742 | 0.028 |

All 100 microsecond group designs retain full rank 16; the largest design
condition number is 1.72. Numerical rank therefore does not explain the failed
phase prediction. The very low minimum coefficient projection coherence and the
fact that a constant predicts the exact held phase better than the fitted affine
trend show that the estimated per-group phase is noisy or mixture-sensitive.

No shared CFO or common phase was imposed. The per-source/per-receiver template
frequencies are independent frozen values. The sealed calculation produced a
coefficient-coordinate slope of −94.19 rad/s and, after adding the signed
template cross-receiver/source-difference rate of +8.69 rad/s, a transported
model-coordinate slope of −85.50 rad/s. A post-replay audit found nine adjacent
training increments above 2.5 rad, a maximum of 3.123 rad, across random-group
gaps as large as seven groups. The unwrap is therefore ambiguous and the slope
must be treated as an abstention, not as a physical rate. The held residuals are
also diffuse, the phase gauge is conditional on the fixed templates, and fitting
an affine trend removes the derivative that a velocity interpretation needs.

The outcome is useful negative evidence. The 28.2 s snippet supports conditional
two-component waveform prediction and nearly compatible receiver offsets, but
does not support stable local differential phase. Further optimizer work on this
snippet is not warranted. The next gate should improve source association and
source-dependent receiver/channel calibration on separately selected dwells,
then repeat the same whole-group held phase test. Geometry or motion fitting
should begin only after that test predicts held phase with high concentration;
the previously measured roughly 2 microradian residual after affine per-dwell
nuisance remains far below what this replay identifies.

Reproducible artifacts: [seal](figures/2026_09_23_local_differential_phase/seal.json)
and [result](figures/2026_09_23_local_differential_phase/result.json).
