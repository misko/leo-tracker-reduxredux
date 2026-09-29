# Two-lag resampled omit-power proposals

The sealed variants retain exactly two periodic-resampled lag features:
`lag1+lag3`, `lag1+lag5`, and `lag3+lag5`. Each removes the other lag before
reference-template FFT construction and before per-window folding,
correlation, percentile ranking, and combined ranking. Power remains omitted.

All retain the fused runner's 11 windows × two receivers, four proposal
centres, radius-two regions, eight candidate inventory, outer CPU timer, NEON
conditioned moments v2, and FP64 final GLRT.

Every variant has host, ASan/UBSan, and ARM cross-build receipts. Host and
sanitizer executed all-rate periodic resampling checks (zero, wrap tail,
circular shift, mapping, and native spacing), all-rate two-lag mask/zero-input
checks, plus inherited final-reuse, fine-budget, and moment-accuracy tests.
No ARM binary or saved-IQ evaluation was run here.
