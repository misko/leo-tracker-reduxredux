# Rank-only squared-magnitude proposal

This bounded research variant starts from frozen fused V4. It changes only the
three lag-feature proposal correlations. Each inverse-FFT real and imaginary
component is normalized before computing `re*re + im*im`; combined proposal
ranking consumes that squared magnitude directly and avoids a `hypotf` for
every cell. The omit-power feature mask, NEON fold/radix ranker, proposal count,
radius-two regions, search, conditioned screen and final FP64 GLRT are unchanged.

The flat-feature gate remains in the original magnitude domain. It takes the
square roots of the minimum and maximum squared scores before applying the
existing `16*FLT_EPSILON` tolerance. Normalization still uses the bounded
existing division; no reciprocal approximation was added.

`python3 build.py` builds host, sanitizer and ARM artifacts. Host and sanitizer
run final-reuse, fine-budget, moment-accuracy, and rank-only component tests.
The latter covers ordering, the flat gate, zero input and CI16 extremes at 2.5,
5, 7.5 and 10 MS/s. ARM is cross-built only.

`../../.venv/bin/python audit.py --all-rates` compares the rank-only fused
runner with the frozen omit-power proposal feeding the frozen NEON-moments V2
search. `audit.json` records exact candidate parity on eight saved dwells, two
template edges at each supported rate. This small audit does not establish a
speed benefit or full-cohort equivalence; both remain unclaimed pending the
serialized ARM and 704-dwell evaluations.
