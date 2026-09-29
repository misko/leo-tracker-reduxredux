# Within-dwell standard GLRT frequency agreement

On the 152-dwell 2.5 MS/s portion of the standard 704-dwell DS7 benchmark,
the median nearest-prior tracking-CFO difference is 40.8 Hz between adjacent
windows and 322.9 Hz between the first and last windows. However, the high
quantiles contain large jumps: the 95th percentile is about 227 kHz.

For every later positive candidate, compare its tracking CFO to the nearest
positive CFO in the specified earlier window, on the same receiver and in
the same dwell. There is no frequency-distance prefilter. Separate baseline
candidate entries stay in the denominator, including duplicates. A previous
window without a positive is counted explicitly, not assigned zero error.

| Window-start separation | Median absolute difference, prior bank available | Within +/-500 Hz, prior available | Within +/-8 kHz, prior available | Within +/-8 kHz, all later positives |
|---|---:|---:|---:|---:|
| 10 ms | 40.8 Hz | 3,262/3,846 (84.82%) | 3,276/3,846 (85.18%) | 3,276/4,164 (78.67%) |
| 20 ms | 72.1 Hz | 2,808/3,401 (82.56%) | 2,835/3,401 (83.36%) | 2,835/3,749 (75.62%) |
| 50 ms | 160.7 Hz | 1,829/2,264 (80.79%) | 1,857/2,264 (82.02%) | 1,857/2,485 (74.73%) |
| 100 ms | 322.9 Hz | 270/356 (75.84%) | 296/356 (83.15%) | 296/398 (74.37%) |

Each dwell contains 11 overlapping 20 ms windows. The 100 ms comparison is
0--20 ms versus 100--120 ms. Adjacent windows share half their IQ; their
agreement therefore is not independent confirmation. The standard active
decision requires non-overlapping windows, at least 20 ms apart.

These are frequency-bank proximity statistics, not verified physical-signal
tracks or recovered GLRT detections. Nearest-frequency association can be
optimistic, permits many-to-one matches, ignores timing identity and does not
address new signals or original hypothesis multiplicity. Large differences
can reflect a different signal, an absent earlier hypothesis, or a frequency
alias; their concentration near 227 kHz is consistent with the alias-branch
behavior in the earlier direct-GLRT experiment, not proof of rapid physical
Doppler drift. There is no alias wrapping in this calculation.

A local search of hundreds of hertz may serve the stable majority, but a
narrow-only policy would miss many standard candidates. A useful tracker
needs multiple hypotheses, an alias-resolution policy and blind discovery or
fallback. These measurements do not establish the CPU cost of such a policy.

`summary.json` records all four sample rates, pooled and per-rate counts,
quantiles, missing-history denominators and the frozen standard-row hash.
`analyze.py` reads only original repeat-zero rows; `test_analyze.py` checks
receiver separation, missing history, duplicate accounting, large jumps and
window separation. All three tests pass. No new IQ analysis or RF collection
was performed.
