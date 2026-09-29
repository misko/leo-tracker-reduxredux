# Four-frequency NEON conditioned moments

The optional `LEO_NEON_CONDITIONED_MOMENTS` macro changes only the approximate,
regular 100 Hz conditioned-screen loop used by preferred final-reuse f2
raw-condition builds. It evaluates four frequencies together, retains all 16
frames, all 41 bins, and fifth-order block moments, and accumulates the
approximate block products in FP32. The exact FP64 rechecks and final GLRT are
unchanged.

`build.py` builds host, sanitizer, and Cortex-A9 NEON artifacts. The component
test compares the new path with the original FP64-accumulator moment path over
four deterministic input patterns at every supported rate and reports measured
maximum absolute and relative magnitude error. ARM artifacts are build-only.
