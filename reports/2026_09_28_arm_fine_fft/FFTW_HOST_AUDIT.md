# FP64 FFTW host audit

The FP64 FFTW backend is scientifically equivalent to the previously qualified
built-in FP64 backend across all 704 sealed dwells. The comparison covered
15,488 receiver/windows and all 19,581 positive candidates. It found no new
backend-to-backend candidate or window mismatch.

The largest acquired-CFO difference was `5.82e-11 Hz`, the largest tracking-CFO
difference was `1.16e-10 Hz`, and the largest final score difference was
`2.18e-15`. Epochs, coarse rankings, refined epochs, frame support, and fine CFO
bins were identical. These differences are far below the existing 2e-6 Hz CFO
and 2e-9 score comparison tolerances.

Both backends retain the same single known comparison against the sealed
original baseline: ordinal 306, receiver 0, probe 3 reports `ordered_field`.
This is the previously documented coarse-screen negative-candidate change. It
is not introduced or enlarged by FFTW. The independent backend comparison uses
the qualified built-in output directly so that this baseline issue cannot be
miscounted as an FFTW regression.

The metadata-balanced 64-dwell cohort independently recovered 1,669/1,669
positives with no baseline errors and no backend mismatch. The 64- and
704-dwell compressed rows, manifests, executed sources, build receipt, and both
compressed and original row hashes are archived under `fftw-results/`.

This audit establishes host numerical equivalence. ARM timing and target
behavior are separate evidence owned by the ARM benchmark; no hardware was
accessed during this audit.
