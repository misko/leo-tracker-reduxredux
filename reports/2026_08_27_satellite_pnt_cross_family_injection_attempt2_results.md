# Satellite PNT paired cross-family Qin injection results

Status: opened-development known-truth measurement evidence; no model-selection gate, posterior odds, satellite identity, or positioning claim.

The three rows below are the independent units. Each row contains a catalogue-orbit truth arm and a center-matched radio-linear truth arm on the same frozen hard-null background. The six arms are not six independent experiments.

| Background pair | Orbit train/future usable | Orbit future RMS (Hz) | Radio train/future usable | Radio future RMS (Hz) |
|---|---:|---:|---:|---:|
| `hard-null-062228` | 897/597 | 54.964131 | 893/599 | 57.315534 |
| `hard-null-105640` | 896/598 | 57.192064 | 897/599 | 54.256404 |
| `hard-null-111222` | 894/600 | 56.745010 | 897/599 | 53.522485 |

The orbit truth objects were selected using TLE geometry only, before background IQ was read. Even Qin supplies training rows; odd Qin supplies future rows. Every opportunity and no-result is retained in the machine-readable evidence.

This artifact measures the front-end response to paired known truth. Catalogue-versus-radio predictive discrimination and covariance scaling remain separate downstream analyses.
