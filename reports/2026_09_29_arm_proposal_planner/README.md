# Proposal FFTW planner experiment

This bounded experiment compares `FFTW_ESTIMATE` with `FFTW_MEASURE` for the
persistent proposal bank only. Both forward and backward plans are created in
`bank_init` before reference data is written to the planner buffers, because
MEASURE may overwrite them. Reference spectra are populated afterward.

Planning uses monotonic wall time and is emitted as `planning_wall_ms` beside
the planner name. Per-window `timings_ms.total` begins in `run_window`, so setup
is excluded. The qualified exact-order NEON fold is unchanged. Fine-frequency
plans are outside this experiment.

Host component tests execute bounded estimate and measure plans, reference
construction, and correlation. ARM planner and exact-fold parity tests are
cross-built only; target execution and the at-most-60-second planning timeout
belong to the serial hardware runner.
