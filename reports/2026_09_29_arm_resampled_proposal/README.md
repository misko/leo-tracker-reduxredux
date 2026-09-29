# Periodically resampled proposal FFT experiment

This bounded candidate keeps all 16 folded frames and the original lag 1/3/5 and power features. It periodically linearly interpolates each original feature lattice to the next power of two, applies the FP32 FFT correlation there, and maps selected peak bins back with `round(k * original_length / fft_length)`. The five-sample exclusion radius is enforced after mapping on the original circular lattice.

The four rate pairs are 3333 to 4096, 6667 to 8192, 10000 to 16384, and 13333 to 16384. JSON rows preserve the existing CLI and `top4`/`top32`/`scores` fields and add transform, length, factor, peak-grid, and distance metadata. The metadata makes explicit that `--scores` arrays live on the resampled FFT lattice.

Build with `python3 build.py`. The host tests cover zeros, periodic wrap interpolation at the tail, circularly shifted sources, nearest original-bin mapping, original-grid peak spacing, scalar fold sanity, and all four rates. The ARM artifacts are cross-compiled only; no ARM measurement or scientific recovery claim is included. Actual GLRT auditing is required because this changes only the approximate proposal stage.
