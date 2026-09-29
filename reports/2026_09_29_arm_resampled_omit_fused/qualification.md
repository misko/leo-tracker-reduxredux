# Resampled omit-power fused proposal prototype

This bounded prototype combines the established periodic-linear resampling to
the next power-of-two FFT length with the fused V4 proposal's omit-power mask.
It retains 11 windows × 2 receivers, four proposal centres, radius-two regional
searches, 16-frame coarse processing, and the NEON conditioned-moments v2
search path. The final GLRT remains the existing FP64 scorer.

The proposal computes only lag-1, lag-3, and lag-5 components. It ranks each
non-flat component on the resampled FFT grid, sums those percentiles, then
maps selected peaks back to native proposal bins before enforcing the existing
five-native-sample circular separation. The removed power component is neither
folded nor correlated under `LEO_PROPOSAL_OMIT_POWER`.

`build.py` produced host, ASan/UBSan, and ARM cross-build receipts. It did not
execute ARM code or process IQ. Host and sanitizer executed the all-rate
periodic-resampling checks (zero input, periodic wrap tail, circular shift,
FFT-to-native mapping, and native-grid peak spacing), the all-rate omit-power
zero-input component path, and the inherited final-reuse, fine-budget, and
conditioned-moment accuracy checks. The moment comparison reported maximum
absolute error `0.000854492188` and maximum screen-normalized error
`0.00126164407` over four rates, 41 bins, and 16 frames.

No timing or recovery claim is made here. The root agent owns serialized ARM
execution and the full 704-dwell standard-hit audit; proposed savings must be
measured rather than inferred from the resampling and feature removal.
