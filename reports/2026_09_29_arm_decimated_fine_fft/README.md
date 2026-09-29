# Factor-5 decimated fine FFT feasibility prototype

## Decision

Stop before ARM execution or cohort qualification. The scalar circular FIR preprocessing makes the isolated host operation slower than the original full FFT, so this implementation does not pass the requested plausibility gate.

## Prototype

The prototype keeps the 500 Hz grid by demodulating each requested band to its aligned center, applying a circular 24-tap Hamming-windowed low-pass FIR, decimating by five, and executing an `N/5` FFT. Original lengths 5000/10000/15000/20000 become 1000/2000/3000/4000. It retains every weighted sample before filtering and corrects each reported magnitude for the known FIR response and factor-five FFT amplitude. Fine-cache keys contain both epoch and aligned band-center bin. Per-center tap modulation and one oscillator step avoid per-sample trigonometric evaluation.

The component test compares 12-, 24-, and 32-tap filters with direct DFT magnitudes for strong in-band tones, two-tone input, and an out-of-band alias at every rate. The 24-tap candidate passes the bounded magnitude checks. Existing full-search and conditioned-moment tests also pass on host and sanitizer, and the sources cross-compile for ARM. These are component results only.

## Feasibility measurement

For 20 repetitions at each of the four rates, the optimized host FFTW full transforms took `0.002455 s` in aggregate. Circular 24-tap filtering plus the factor-5 transforms took `0.005022 s`, or about `2.05x` as long. Sanitizer measurements show the same direction (`0.004423 s` versus `0.011857 s`).

The cause is visible in the operation count: computing only decimated outputs still requires 24 complex taps for each of `N/5` outputs, or 4.8 complex FIR multiply-accumulates per original sample, plus demodulation and the smaller FFT. The current scalar preprocessing outweighs the FFT reduction on the host. No ARM timing, saved-IQ recovery, or subsecond claim is made. A NEON polyphase FIR could change the target balance, but it is outside this bounded prototype and would need a new experiment.
