# FP32 FFTW transfer on new DS5 development data

The unchanged unseeded strided FP32 FFTW detector preserved the stable packed
V4 FP64 reference on the frozen new-development dataset. All 129 reference
positives matched within the preregistered 2 us and 8 kHz gates, including all
67 positives at 5 MS/s. There were no lost positives, additional positives,
selected-window changes, rank-order changes, or projected-epoch-array changes.

| Cohort | RX visits | Reference positive | Retained | Added | FP64 CPU | FP32 CPU | CPU speedup |
|---|---:|---:|---:|---:|---:|---:|---:|
| All new development | 256 | 129 | 129 | 0 | 795.234 ms | 490.922 ms | 1.620x |
| 2.5 MS/s | 128 | 62 | 62 | 0 | 270.428 ms | 167.183 ms | 1.618x |
| 5 MS/s | 128 | 67 | 67 | 0 | 524.806 ms | 323.739 ms | 1.621x |

The largest paired-observation drift over all real cases was
`1.086e-7` in exact-minus-control margin, `9.738e-5 Hz` in CFO, and
`2.719e-6` samples in circular epoch. For retained positives, maximum CFO drift
was `4.804e-5 Hz` and maximum circular epoch drift was `2.808e-7` samples.
Rank scores were unchanged.

The fixed controls also transferred exactly. At each of 2.5 and 5 MS/s, all
four pilot receiver cases were positive and all four noise plus four tone
receiver cases were negative for both implementations.

The result passes the frozen scientific transfer gate. Its 1.620x aggregate CPU
speedup is about 6.17 times short of a 10x full-call target. Timings cover
receiver ingress and the complete detector call after one warmup, using the
median of three counterbalanced repetitions. They exclude IQ loading and
hashing and do not establish ARM or pipeline performance.

`results.json` contains all rows, timings, numerical drift, source hashes, and
the pre-outcome source lock. The packed FP64 baseline is reference-relative
detector evidence rather than physical truth; misses remain unknown rather than
physical negatives.
