# FP32 final matched-filter experiment

This experiment changes only the per-symbol complex matched-filter dot products
inside final GLRT scoring. It retains 16 frames, 64 symbols, FP64 energy and
normalization, and the existing FP64 residual-FFT selection. Rotated exact and
control templates are narrowed locally inside the timed GLRT call. ARM uses
four-lane NEON accumulation; host uses the same four stable FP32 partial sums.

The approximation is explicit and has no FP64 fallback. It requires saved-IQ
science qualification before selection. ARM artifacts are cross-build only.
