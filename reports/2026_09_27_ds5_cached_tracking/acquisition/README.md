# Seeded acquisition comparison

This development-only experiment compares the common packed, unseeded blind
detector with the V4 natural-stride rank-seeded detector. The candidate receives
no automatic blind fallback, so a missing, incomplete, or mismatched proposal is
reported as a miss.

The default frozen run uses one warmup and three counterbalanced repetitions for
all 128 development visits and both receivers. Previous pilot, noise, and tone
controls at 2.5 and 5 MS/s run afterward and never tune the method. Holdout IQ is
not opened.

The runner also accepts `--candidate-library` and `--no-candidate-seeded` for a
separately named development receipt. This keeps the same matching and control
harness available to isolated native variants without changing the frozen default
experiment.
