# Armijo optimizer through the compact v5 final decision

Keeping the final selection recovered the DS26-0287 cavity regression. The Armijo finish returned within 0.06 m and 0.28 m of the original no-repair v5 positions in the two calibration arms. The locked DS26-0066 run reached final reassociation and failed on a phase-array index. Three of four primary runs returned both fixes. [Locked predictions](prediction-lock.json) · [Protocol](PROTOCOL.md) · [All position and RF scores](scores.csv)

Each run used original capture-era native factors, fresh graph preparation, the same causal TLE archive and the original 25 km search tile. The wrapper substitutes the bounded Armijo optimizer at the same hook as the Armijo cavity worker. It then runs the stock compact finish with its original residual screening, checked adoption, RF influence trigger, guarded reassociation and final paired selection. The position hook takes local east and north in kilometres with half-width 12.5 km. Its 0.020 km stopping step is 20 m, and the 0.001 km numerical Jacobian step is 1 m.

## Geographic comparison

Each pair gives `c = 0` followed by fitted `c`. Distances are in kilometres. The DS26-0287 stock compact finish has no authenticated archival receipt. All four original v5 role outcomes are included in the score sheet. [Original role positions](original-roles.json)

| Recording | Armijo finish | Armijo cavity | Stock cavity | Stock compact finish | Original no-repair v5 |
|---|---:|---:|---:|---:|---:|
| DS26-0066 | Failed | 2.389 / 2.370 | 2.389 / 2.370 | 1.244 / 1.218 | 1.244 / 1.218 |
| DS26-0287 | 0.502 / 0.439 | 0.752 / 0.673 | 0.773 / 0.689 | Missing | 0.503 / 0.440 |
| DS26-0002 | 0.561 / 0.578 | 0.561 / 0.578 | 0.667 / 0.701 | 0.665 / 0.697 | 0.665 / 0.697 |
| DS29-0082 | 0.567 / 0.516 | 0.567 / 0.516 | 0.567 / 0.517 | 0.567 / 0.517 | 0.567 / 0.517 |

- **DS26-0287** added 32 observations in each arm through the checked residual path. It had zero admitted reassociations. Geographic error fell by 250 m with `c = 0` and 234 m with fitted `c`, compared with the Armijo cavity. The selected addition emitted its saved RF objective and ownership but had no conditional aggregate RMS field.
- **DS26-0002** rejected its residual addition while the logged stock compact finish accepted one. The candidate stayed at its Armijo cavity endpoints and retained 3,232 observations in each arm. Fitting `c` increased geographic error by 17 m and lowered conditional RMS from 75.824 to 75.689 Hz.
- **DS29-0082** found no qualifying additional family and returned the Armijo cavity endpoints. The candidate lay 1.15 m and 1.03 m from the original arms. Fitting `c` lowered geographic error by 50 m and conditional RMS from 97.004 to 96.684 Hz.

The archived original v5 `residual_rms_hz` is the publication-stage RF residual. The compact workers report their selected likelihood's conditional Doppler RMS where available. The score sheet keeps these fields independent and leaves absent conditional values blank. [Matched conditional and publication RF scores](scores.csv)

## Runtime from archived detector factors

The current one-CPU replay clocks include projector compilation, worker launch, fresh tracking and numerics, and result handoff. CPU seconds include the supervising process and its waited children. Peak RSS is the largest waited subprocess. Archived controls used other CPUs and timings, so their wall times are component observations from a separate run. The fresh DS26-0002 Armijo cavity took 56.72 s wall and 53.88 s CPU on the same CPU as the finish, after the finish ran. [Primary receipt](positions.jsonl.gz) · [Armijo cavity controls](armijo-cavity-positions.jsonl.gz) · [Stock finish controls](stock-finish-positions.jsonl.gz)

| Recording | CPU | Finish wall / CPU (s) | Peak RSS (KiB) | Inner Armijo wall (s) | Largest named successful stage (s wall) |
|---|---:|---:|---:|---:|---|
| DS26-0066 | 6 | 198.95 / 177.99 | 1,800,620 | — | Worker failed during final reassociation |
| DS26-0287 | 1 | 144.35 / 128.01 | 1,729,276 | 7.86 | Reassociation admission, 26.44 |
| DS26-0002 | 6 | 127.27 / 119.64 | 1,763,200 | 5.63 | Initial position, 19.39 |
| DS29-0082 | 1 | 93.22 / 86.40 | 1,298,152 | 1.19 | Reassociation admission, 24.83 |

## Separate DS26-0066 ordered phase retry

The failed run's accepted residual addition appended NORAD 66468 at sky index 1375. The seed's catalogue-indexed initial phase array still had 1,375 elements. Final reassociation then appended NORAD 68047 and one zero initializer to the short seed, making index 1376 inaccessible. The retry independently verifies the original ordered identity prefix and the one adopted sky slot before supplying its stock zero-second initializer. The original 1,375 starts, 21 prior means and both 21-element phase-reference arrays are preserved in the retry receipt. The recovered candidate retains the original causal catalogue, optimizer, priors, admission and selection. Both worker requests match after removing the output paths. [Original traceback](phase-retry-primary-traceback.txt) · [Ordered sky and phase arrays](phase-retry-ordered-inputs.json.gz) · [Retry receipt lock](phase-retry-prediction-lock.json)

The retry adopted 67 residual observations per arm and selected `62025_to_68047`, the same signed reassociation as the stock finish. Error was **1.209 / 1.191 km**, down from **2.389 / 2.370 km** at the Armijo cavity. The retry positions were 42.77 / 34.91 m from original no-repair v5. Conditional Doppler RMS was 69.872 / 69.940 Hz, within 0.003 Hz of the stock compact finish in both arms. Fitting `c` reduced geographic error by 18 m and increased conditional RMS by 0.067 Hz. The separate replay took 185.50 s wall and 180.85 s CPU on CPU 1, with peak worker RSS of 1,809,312 KiB and 32.04 s wall in final reassociation. The predeclared four-recording result retains the original failed attempt. [Separate retry scores](phase-retry-scores.csv) · [Separate retry position](phase-retry-positions.jsonl.gz)

## Reproduce the primary trial

The report's source lock is already published. Use a new scratch directory and run the two CPU lanes concurrently or independently. Each lane runs cases sequentially.

```bash
.venv/bin/python -B -m tools.pipeline_eval.qualification.armijo_finish_trial lock  # only when generating a new lock
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 1 .venv/bin/python -B \
  -m tools.pipeline_eval.qualification.armijo_finish_trial run DS26-0287 --work /tmp/armijo-finish
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 1 .venv/bin/python -B \
  -m tools.pipeline_eval.qualification.armijo_finish_trial run DS29-0082 --work /tmp/armijo-finish
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 6 .venv/bin/python -B \
  -m tools.pipeline_eval.qualification.armijo_finish_trial run DS26-0066 --work /tmp/armijo-finish
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 6 .venv/bin/python -B \
  -m tools.pipeline_eval.qualification.armijo_finish_trial run DS26-0002 --work /tmp/armijo-finish
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 6 .venv/bin/python -B \
  -m tools.pipeline_eval.qualification.armijo_finish_results cavity --work /tmp/armijo-finish
.venv/bin/python -B -m tools.pipeline_eval.qualification.armijo_finish_results publish \
  --work /tmp/armijo-finish --out /tmp/armijo-finish-report
.venv/bin/python -B -m tools.pipeline_eval.qualification.armijo_finish_results score \
  --out /tmp/armijo-finish-report
```

Reproduce the separately locked retry from the retained failed worker receipt and traceback. The two files reproduce the retry lock's exact failure fingerprint. The new worker reads the same frozen case and validates its scientific inputs before numerical inference.

```bash
report=reports/2026_11_19_receiver_screening/armijo-finish
mkdir -p /tmp/armijo-first/position
cp "$report/phase-retry-primary-receipt.json" /tmp/armijo-first/prediction.json
cp "$report/phase-retry-primary-traceback.txt" /tmp/armijo-first/position/worker.log
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 1 .venv/bin/python -B \
  -m tools.pipeline_eval.qualification.armijo_finish_phase_retry run \
  --prior /tmp/armijo-first/prediction.json --out /tmp/armijo-finish-retry
```
