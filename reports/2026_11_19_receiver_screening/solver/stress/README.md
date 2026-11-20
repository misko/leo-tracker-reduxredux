# Deliberate cavity-cutoff stress cases

The two outcome-selected recordings test whether changing only the position optimizer repairs the previously observed gap between compact cavity and original no-repair v5. It preserved that gap on both recordings. The largest Armijo-to-stock endpoint shift was 20.83 m. Armijo's fitted-calibration error still exceeded original v5 by 1.152 km on DS26-0066 and 0.233 km on DS26-0287. These cases are reported separately from the independent confirmation set. [Protocol](../CONFIRMATION.md) · [Scores](scores.json) · [Prediction lock](prediction-lock.json)

| Recording | Original no-repair error, `c = 0` / fitted | Stock compact error | Secant compact error | Armijo compact error |
|---|---:|---:|---:|---:|
| DS26-0066 | 1.244 / 1.218 km | 2.389 / 2.370 km | 2.384 / 2.365 km | 2.389 / 2.370 km |
| DS26-0287 | 0.503 / 0.440 km | 0.773 / 0.689 km | 0.752 / 0.673 km | 0.752 / 0.673 km |

Armijo and stock had identical observation and track counts and cavity-offer decisions. The RMS shifts against stock were at most 0.00044 Hz. The original v5 report's RMS is calculated on its associated observations at a later pipeline boundary. The data retain its per-arm residuals separately. [Per-arm scientific records](scores.json)

Armijo ran in 123.18 s on core 8 and 94.15 s on core 9 from stored native factors through compact cavity. Historical stock compact wall was 159.80 s with the core unrecorded and 140.76 s on core 10. Original no-repair wall was 531.91 s and 506.85 s on core 16 through its scientific output. The source records come from separate runs and the original boundary extends beyond compact cavity. [Armijo](armijo-positions.jsonl.gz) · [Stock cavity](reference-positions.jsonl.gz) · [Original no-repair](original-positions.jsonl.gz)

The two input-bound secant controls came from the separate full-roof replay. Their endpoints were within 7.28 m of Armijo on DS26-0066 and 0.28 m on DS26-0287. Conditional RMS changed by at most 0.00083 Hz. Secant used 857 and 606 residual evaluations, compared with Armijo's 825 and 630. Secant wall times were 136.82 s on core 14 and 101.83 s on core 18. [Secant stress receipts](secant-positions.jsonl.gz)
