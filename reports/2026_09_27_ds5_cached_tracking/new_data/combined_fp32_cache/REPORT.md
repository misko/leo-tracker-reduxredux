# Combined V6 cache and FP32 FFTW fallback

The single frozen server run measured the actual V6 causal cache plus the
unchanged unseeded FP32 FFTW blind fallback. It did not multiply independently
measured speedup ratios.

| Cohort | RX visits | FP64 reference CPU | Combined CPU | CPU speedup | Reference positive | Matched | Lost | Added |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| All | 256 | 836.349 ms | 426.704 ms | 1.960x | 129 | 120 | 9 | 9 |
| 2.5 MS/s | 128 | 283.697 ms | 149.965 ms | 1.892x | 62 | 60 | 2 | 2 |
| 5 MS/s | 128 | 552.651 ms | 276.739 ms | 1.997x | 67 | 60 | 7 | 7 |

The preregistered identity gate **failed**. It required retention of every
packed FP64 reference positive with no additional candidate positives under the
2 us and 8 kHz reference-match gates. The combined result retained 120 of 129,
lost nine, and added nine.

All nine discrepancies were accepted V6 cache hits. The nine mismatched
positive pairs differed by 90.374–371.414 us or 39.331–151.942 kHz. The 120
matched positives stayed within 1.200 us and 430.410 Hz. This reproduces the
known cache-association limitation rather than a new FP32 fallback failure.

The fallback backend is hash-pinned
`libfft32_fftw.so` and its build receipt states that every FFT uses FP32 FFTW.
It handled 182 receiver visits. Relative to the independently timed packed FP64
reference on those same visits, it produced zero selected-window changes, zero
rank-order changes, retained all 55 fallback reference positives, and had no
fallback extras. Its maximum paired error was `5.697e-7 us` and
`9.738e-5 Hz`.

The candidate made 126 cache attempts and accepted 74; 182 visits used blind
fallback. Candidate timing includes causal state overhead plus the actual cache
or fallback call. Each action had one warmup and three measured repetitions;
the packed reference order alternated by visit and receiver. Measurements use
process CPU and monotonic wall time and exclude IQ loading and hashing.

Every persisted row states that the reference was not used for state and records
`candidate_observation` as the only possible state-update source. The adapter's
state-update port accepts only the candidate observation. These tests establish
the causal data path in this isolated replay; the packed reference remains an
independent same-visit comparator.

This is development-only server evidence. It does not open holdout data,
exercise ARM hardware, collect RF, or establish physical truth from detector
agreement.
