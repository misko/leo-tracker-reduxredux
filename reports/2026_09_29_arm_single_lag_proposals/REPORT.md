# Single-lag proposal quality floor

The sealed `lag1`, `lag3`, and `lag5` variants each retain one periodic
resampled proposal feature and omit the other two lags and power before
template FFT, folding, correlation, and ranking. All retain 22 windows per
dwell, four centres, radius-two regions, eight candidates per window, NEON
moments v2, and the FP64 final GLRT.

Host, ASan/UBSan, and ARM cross-build receipts include all-rate feature-mask
and zero-input checks, plus all-rate resampling zero/wrap/shift/mapping/native
spacing checks. No ARM binary was run.

The only saved-IQ execution was the prescribed 32-dwell panel against
`host32-fast-f2-raw`, using the sealed omit-power feature rows. Every variant
returned 704 windows and 5,632 candidate entries.

| retained lag | standard hits | reference hits | native positive hits | threshold result |
| --- | ---: | ---: | ---: | --- |
| lag1 | 822 | 843 | 1,674 | stop: below 829 |
| lag3 | 825 | 843 | 1,714 | stop: below 829 |
| lag5 | 824 | 843 | 1,652 | stop: below 829 |

None reached the 829/843 expansion gate, so no full-704 saved-IQ evaluation
was performed. These results quantify the single-feature quality floor; they
do not make a runtime or ARM claim.
