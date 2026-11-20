# Embedded bounded orbit and receiver fit

The C11 solver fits east and north offsets, four clock biases, four clock drifts, optional RF calibration `c`, and one phase correction for each owned orbit. A single track contributes to exactly one phase column. The solver accumulates a small receiver Gram block and one cross vector plus diagonal per orbit. It eliminates free phase corrections by a Schur complement and recovers them after solving the receiver block. A feasible active set enforces every original box bound and releases a bound when the gradient calls for doing so. The original phase prior, clock priors, track whitening, loss weights, aliases and receiver bounds enter the same least-squares problem. The position radius uses the original unconstrained covariance convention.

## Recorded endpoints

The two predeclared roof recordings reproduce the sealed native-joint Graph projection and causal catalogue. The host starts after the final native-joint orbit selection and replaces each linear solve in the full fixed-owner nonlinear range-rate fit. The host retains the original held-track publication decisions. AArch64 runs the same C kernel on frozen statistics from each actual linearization, applies the accepted step fractions, and calculates latitude and longitude in C. Original nonlinear RF residuals are evaluated on the returned AArch64 coefficients by the host. Each arm uses the very same assigned tracks and orbit identities.

| Recording | Calibration | Schur error (km) | Original no-repair v5 error (km) | Schur conditional RF RMS (Hz) |
| --- | --- | ---: | ---: | ---: |
| DS26-0036 | `c = 0` | 1.833 | 1.278 | 164.348 |
| DS26-0036 | fitted `c` | 1.016 | 1.208 | 135.176 |
| DS29-0082 | `c = 0` | 1.550 | 0.567 | 249.733 |
| DS29-0082 | fitted `c` | 1.643 | 0.517 | 213.327 |

The AArch64 kernel reproduces the SciPy endpoint within 7 µm in each recorded arm, with absolute conditional RMS changes below 2 × 10⁻⁹ Hz. At the individual linear solves, maximum coefficient differences are below 2.2 × 10⁻¹¹ in the original parameter units. The independent synthetic fixture activates both position bounds and opposite-signed orbit phase bounds in both arms. Its fitted coefficients agree with SciPy within 6 × 10⁻¹³. DS29-0082 shows why RF fit and geography need separate scores. Fitted `c` lowers RF RMS by 36.407 Hz while increasing geographic error by 92.5 m.

[Geographic comparison plot](geographic-comparison.png) · [Measured coordinates and displacement from the four v5 fixes](geographic-comparison.csv) · [Evidence and performance](measurements.json) · [Prediction lock](prediction-lock.json)

## Measured boundary

| Measurement | Result |
| --- | --- |
| Actual selected observations and owned orbits | 2,867 and 30 on DS26-0036. 1,480 and 34 on DS29-0082. |
| Original dense whitened design | 524–932 KiB for one matrix, excluding the separate RF-domain design and work vectors. |
| Compact precomputed statistics and bounds | 4.0–4.8 KiB per linearization. |
| Matched host initial fit including assembly, solve and residuals | 4.64–10.16 ms SciPy and 2.93–5.86 ms Schur across the four arms. Each is the median of 31 alternating paired trials on CPU 17. |
| Host standalone solver with frozen statistics | 3.6–4.9 µs per linear solve. Largest process RSS was about 0.57 MiB. |
| AArch64 under QEMU with frozen statistics | 94–118 µs per linear solve over five batches of 5,000 repeats per linearization. The largest explicit runner and solver heap is 6,077 bytes. The GCC-reported stack path is 2,304 bytes. Emulator process RSS peaked at 8,064 KiB. |

The ARM scope starts with precomputed statistics and host-selected step fractions. Raw IQ acquisition, GLRT, Graph, orbital propagation, whitening, relinearization and held-track validation ran upstream on the host. Emulator wall time is a reproducible software measurement. The entire receiver still needs its independent device memory and deadline measurements.

## Reproduce

The normalized position chart uses the standard screening renderer. The companion plot and CSV can be regenerated from the sealed evidence.

```sh
report=reports/2026_11_19_receiver_screening/factors/embedded-solve
python -m tools.pipeline_eval figures --panel screening --evidence "$report" --arm both --out /tmp/embedded-fit-figures
python -m tools.pipeline_eval.qualification.embedded_solve_figures --evidence "$report" --out /tmp/embedded-fit-figures
```

The standalone fixed-statistics ARM solve can also be rerun without acquisition data, Python, NumPy or SciPy. Install a Linux AArch64 C compiler and QEMU user-mode emulator to run this command.

```sh
aarch64-linux-gnu-gcc -std=c11 -O3 -ffp-contract=off -static \
    tools/pipeline_eval/variants/embedded_solve.c \
    tools/pipeline_eval/qualification/embedded_solve_runner.c -lm -o /tmp/embedded-solve-arm
gzip -dc "$report/DS26-0036-fitted_c-stats.bin.gz" | qemu-aarch64 /tmp/embedded-solve-arm 5000
```

The full qualification uses the repository's frozen native and catalogue archives. Use a new local output directory for another measurement and pin a free core with one BLAS thread.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 17 \
    python -m tools.pipeline_eval.qualification.embedded_solve \
    --work /tmp/embedded-solve-work --out /tmp/embedded-solve-evidence --repeat 5000
```
