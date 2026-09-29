# FP32 GLRT FFT experiment

This experiment retains FP64 matched-filter dots, energy, spectra accumulation,
ceilings, normalization, and selection. It replaces only the FFT executions
inside GLRT with cached FFTWf plans. `short128` narrows the repeated 128-point
transforms; `both` also narrows the final 512-point residual transform. Plans
are workspace-owned and lazily created during the first timed GLRT call.

These are approximate, explicitly tagged research binaries with no fallback.
ARM artifacts are cross-build only.
