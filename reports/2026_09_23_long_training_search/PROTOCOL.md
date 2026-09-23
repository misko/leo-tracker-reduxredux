# First long-TRAIN blind tau-zero search: frozen protocol

Use only the first session in the frozen long-cohort TRAIN partition,
`scan-hop-85afa91453f8847b`. Consume its response-free causal candidate cache,
all eligible tracks spanning at least three seconds, and their saved randomized
frequency masks. Do not use published identities, position seeds, validation or
test sessions, reserved rows, or the receiver reference during inference.

Run two distinct altitude-zero prior searches: Sacramento within 250 km and Reno
within 500 km. Score a deterministic 100 km grid inside each disk. Retain the
best three cells subject to pairwise separation of at least the current grid
spacing, then evaluate a 3-by-3 neighborhood around each retained cell at
successive spacings 50, 25, 12.5, 6.25, 3.125, and 1.5625 km. At every level,
retain the best three diverse in-prior points. Cache duplicate coordinates.
This is a bounded coarse-beam heuristic, not an exhaustive or globally optimal
search. Preserve the two prior results separately.

Fix timing at tau zero. At each point, require exact above-horizon visibility,
then choose each track's causal candidate identity and constant frequency offset
using training rows only. Score tracks by duration-weighted capped-800-Hz
training RMS. An unmatched track receives the 800 Hz penalty. Linear state
interpolation uses the regular one-second cache and its independently qualified
sub-hertz approximation.

Hash and save both inferred positions, identities, offsets, objectives, and full
search traces before opening reserved frequency rows or the reference coordinate.
Post-seal evaluation reports reserved capped/uncapped RMS and geographic error.
Neither metric may alter the search policy or select between priors.

The run is conditional on the regional response-free candidate filter, the
coarse-beam heuristic, altitude zero, a single scan, and tau zero. Cap the first
scan near five minutes. No long-cohort validation/test evidence, prospective
evidence, deployment, or RF collection is included.
