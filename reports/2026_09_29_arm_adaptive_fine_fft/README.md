# Adaptive fine-frequency endpoint FFT prototype

This experiment starts from the preferred NEON conditioned-moments v2
standalone search and changes only its fine-frequency estimator.  For each
epoch it computes the first available endpoint FFT, scores the candidate's
requested frequency interval on the unchanged 500 Hz grid, and finds the
strongest local maximum outside plus or minus two bins of the winning bin.  It
computes and averages the second available endpoint only when

`best score < LEO_FINE_ADAPTIVE_RATIO * strongest non-neighbor local maximum`.

The three cohort binaries set that ratio to 1.25, 1.5, and 2.0.  A higher ratio
therefore sends more candidates through the second FFT.  This is an explicit
proposal-stage approximation: a first endpoint can look unambiguous even when
the second endpoint would change the averaged fine-frequency peak.  Candidate
selection and all downstream FP64 GLRT frames, constants, normalization, and
interpolation code remain unchanged.

The cache stores endpoint spectra independently.  Dominance is evaluated for
every requested frequency interval, including cache hits, so a narrow request
that used only endpoint one cannot prevent a later wider request for the same
epoch from computing endpoint two.  `fine_fft_first_only` counts calls resolved
from endpoint one; `fine_fft_second_computed` counts actual lazy second FFTs.

Run `python3 build.py` to recreate host, sanitizer, and ARM cross-builds.  The
host and sanitizer builds execute final-reuse, conditioned-moment, and adaptive
fine FFT tests.  The adaptive test covers all four rates, a dominant tone, an
ambiguous two-tone input, non-neighbor exclusion, a later wider cache request,
and minimum-length partial input.  ARM binaries are cross-built only; target
execution and cohort qualification are intentionally left to the serialized
runner.  Exact commands, source hashes, binary hashes, and test output are in
each `builds/*/build-receipt.json`; `build-manifest.json` seals those receipts.

No speed or scientific-quality benefit is claimed by these build artifacts.

## Full host qualification

The sealed 1.25 and 1.5 binaries were subsequently run over the 704-dwell,
15,488-window cohort using the float-proposal features, top four regions, and
radius two.  Against 19,581 standard positive hits, ratio 1.25 recovered 19,208
and ratio 1.5 recovered 19,213.  The unchanged two-endpoint NEON-moments
reference recovered 19,249, so these approximations lose 41 and 36 recovered
hits respectively on this audit.

Ratio 1.25 avoided 15,369 of the reference's 155,710 endpoint transforms
(9.87%); ratio 1.5 avoided 9,997 (6.42%).  The `first_only_requests` totals are
36,539 and 27,728, but those are request counts and include cache hits.  They
must not be reported as FFTs saved.  Host timings are search-only observations
and are not an ARM speed claim.  `host704-results.json` binds the aggregate
results to each rows file and to the standard-hit and counter audits.
