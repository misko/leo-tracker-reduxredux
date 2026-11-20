# Independent eight-recording confirmation

The locked Armijo fit returned both calibration arms on all eight independent secant-confirmation recordings. It matched stock cavity's prepared observation and track counts and cavity-offer decisions. All initial branches ran five phase updates. The largest horizontal endpoint differences were **19.12 m versus stock cavity and original no-repair v5**, and **18.37 m versus secant**. All compact comparisons met the 50 m and 1 Hz limits. [Protocol](../CONFIRMATION.md) · [Frozen plan](../confirmation-plan.json) · [Prediction lock](prediction-lock.json)

| Recording | Armijo error, `c = 0` / fitted | Largest shift from stock / secant | Armijo evaluations / secant |
|---|---:|---:|---:|
| DS26-0142 | 0.301 / 0.278 km | 3.71 / 0.15 m | 678 / 685 |
| DS26-0223 | 0.809 / 0.743 km | 19.12 / 18.37 m | 918 / 933 |
| DS26-0301 | 0.652 / 0.675 km | 17.36 / 0.13 m | 480 / 489 |
| DS26-0018 | 0.522 / 0.478 km | 9.24 / 0.88 m | 639 / 663 |
| DS29-0127 | 0.634 / 0.580 km | 15.60 / 3.10 m | 336 / 352 |
| DS29-0316 | 1.007 / 1.011 km | 10.31 / 1.05 m | 681 / 706 |
| DS29-0357 | 0.438 / 0.437 km | 13.57 / 6.83 m | 687 / 707 |
| DS29-0519 | 0.235 / 0.305 km | 18.44 / 0.42 m | 411 / 436 |

Median errors were 0.578 km at `c = 0` and 0.529 km with fitted calibration for Armijo. Stock cavity and original no-repair produced 0.576 km and 0.527 km. The Armijo conditional RF RMS changed by at most 0.00249 Hz from stock or 0.00110 Hz from secant. Fitting `c` lowered Armijo positional error in five recordings and conditional RF RMS in five. Original report RMS uses the original associated observations at its later boundary and is retained separately. [Arm and frequency scores](scores.json)

Armijo used 4,830 residual evaluations versus 4,971 for secant. Its median wall time was 126.16 s on cores 8, 9, 20 and 21. Historical secant's median was 96.13 s on cores 16–19, with stock cavity at 132.96 s on its archived mixed cores. Original no-repair took a median of 274.83 s through its scientific output boundary. These are measurements from separate host runs. The contemporaneous wall comparison is the [two smoke timing pairs](../README.md#fresh-smoke-timing).

[Armijo predictions](armijo-positions.jsonl.gz) · [Historical compact cavity](reference-positions.jsonl.gz) · [Historical secant](secant-positions.jsonl.gz) · [Original no-repair](original-positions.jsonl.gz)
