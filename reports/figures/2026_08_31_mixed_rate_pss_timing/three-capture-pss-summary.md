# Three-capture mixed-rate PSS replay

The candidate-only, rate-generic PSS search was replayed over every continuity-safe block in these
three captures. Each replay searched the 2.5 MS/s RX0 path and the 15 MS/s RX1 path using the native
channel reference appropriate to that capture. No timing lattice crosses a persisted gap.

| Capture | Channel reference | 2.5 MS/s | 15 MS/s | Strongest 15 MS/s evidence |
|---|---:|---:|---:|---:|
| `cap-20260831T040346-3d8c2d6e62bd` | 1,325,117,187.5 Hz | 0 / 60 blocks | 2 / 233 segments; 261 windows | robust z=6.90 |
| `cap-20260831T044729-6a598698a226` | 1,575,117,187.5 Hz | 0 / 60 blocks | 15 / 229 segments; 2,255 windows | robust z=10.32 |
| `cap-20260831T071200-9184cf0ad6cc` | 1,075,117,187.5 Hz | 0 / 60 blocks | 27 / 237 nonempty segments; 3,665 windows | robust z=9.88 |

## Interpretation

`040346` has only two isolated 15 MS/s candidates, at device times 5.80 and 44.39 seconds, with
different frame phases. It is not a persistent timing-lattice detection.

`044729` has one coherent 15 MS/s episode from device time 36.42 to 41.24 seconds. Its folded epochs
occupy only 2,756--2,787 samples modulo the 20,000-sample frame. A linear fit gives +0.078
microseconds of phase drift per second with 0.690 microseconds RMS residual. This is strong,
near-stationary PSS-like frame timing.

`071200` has one coherent 15 MS/s episode from the start of the device axis through 6.78 seconds.
Its phase moves smoothly from 1,185 to 1,968 samples. A linear fit gives +7.736 microseconds of
phase drift per second with 0.593 microseconds RMS residual. This is the clearest moving frame-timing
track of the three. The slope is receiver-relative and combines propagation-delay rate with sample-
clock error; it is not yet an independently calibrated Doppler observable.

None of the three 2.5 MS/s paths passes the declared robust-z >= 6 threshold. Across this set, the
15 MS/s upper-edge projection provides substantially stronger PSS frame-timing evidence. It still
does not contain or validate the full PSS/SSS synchronization bandwidth.

Each capture directory contains the complete JSON replay plus `pss-detection-vs-time.png` and
`pss-frame-phase-vs-time.png`.
