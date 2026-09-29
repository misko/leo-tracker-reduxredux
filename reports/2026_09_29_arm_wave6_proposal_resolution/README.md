# Wave6 half-resolution proposal experiment

This isolated approximation starts from sealed Wave5 final v2.  It retains
the full 16-frame folded lag-1/3/5 input sequences and every downstream search
stage, but periodically linearly resamples each original frame-length sequence
to `next_power_of_two(n) / 2`.  Correlation and rank fusion run on that smaller
power-of-two grid.  Selected bins map back with
`round(k * n / fft_n) modulo n`, and the five-original-sample peak exclusion
remains on the mapped grid.

The four transform lengths are 2,048, 4,096, 4,096, and 8,192 for rates 2.5,
5, 7.5, and 10 MS/s.  Because each length is below the original sequence
length, this discards proposal resolution and is explicitly approximate.
Nothing here claims exact equivalence to the full proposal transform.

The owned resampling test covers all four rates and now requires `fft_n < n`.
It checks zeros, periodic tail interpolation, shifted inputs, the mapped-index
error bound, and minimum peak distance on the original grid.  All inherited
host and sanitizer units pass, and the Cortex-A9 target cross-builds.  No ARM
binary was executed.

The regional32 gate recovers 829/843 reference hits, exactly the expansion
threshold.  On the full 704-dwell DS7 panel it recovers 19,161/19,581 hits,
compared with 19,217 for sealed Wave5 final v2.  The deterministic identity
audit records 65 lost and 9 gained reference hits, a net loss of 56.  Candidate
inventories also change substantially: 46,036 candidate positions in 9,843
windows differ from final v2.

Host mean proposal time is 21.64 ms, including 13.89 ms folding, 2.67 ms FFT
correlation, and 5.01 ms ranking.  This shows a useful resolution/runtime
tradeoff on the host, but the measured recall loss rejects the half-grid form
for the preferred pipeline.  A quarter-grid variant was not expanded because
the half-grid variant already failed full-cohort quality.

The ARM binary is `builds/arm/fused_wave6_proposal_half_arm`, SHA-256
`72648dcb24931ba295e758f08d00a6cbca7c6fcf950cc33122e68eaf23a891b0`.
