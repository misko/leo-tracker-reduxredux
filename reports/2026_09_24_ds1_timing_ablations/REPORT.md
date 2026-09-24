# DS1 timing ablations

`timing_rows.json` normalizes 176 provenance-bound, sealed fixed-identity
timing arms. It retains both complete TRAIN blocks (72 and 79 scans), all
available validation views (1, 6, 16, and the 44/80-scan full blocks), partial
TEST (1/6/16), and both exact full-TEST64 failures. The source artifacts use
DS1 membership, causal caches, original randomized masks, training-profiled
CFO, occupied-second weighting, and the 800 Hz cap. Their per-track identities
are fixed from the respective tau-zero TRAIN baseline; they are not catalogue
reassociation experiments.

The new row-table selection uses only the two complete TRAIN blocks and their
TRAIN capped RMS: scale 5 s is lowest at 279.300 Hz, versus 279.448 Hz at 1 s
and 286.840 Hz at 0.2 s. This selection is recorded as a new frozen
TRAIN-only comparison; it does not rewrite the historical validation-selected
0.2 s global rule or imply that TEST contains an unrun 5 s per-scan arm.

At the full TRAIN blocks, fixed-identity global timing has about 285.97 Hz
(72 scans) and 290.01 Hz (79 scans) TRAIN RMS at the 0.2 s rows. Per-scan
regularization at the frozen 5 s scale lowers those values to about 277.40 Hz
and 281.20 Hz. The corresponding full validation blocks also lower TRAIN
residuals (298.46 to 283.75 Hz for 44 scans; 271.42 to 264.53 Hz for 80), but
frequency residuals are not used to choose a location model or make a location
claim. All 176 rows preserve `held_used_for_fit=false` and
`truth_used_for_fit=false`.

`fractional_diagnostic.json` supplies the bounded common-tau resolution check
on the first TRAIN 16-scan case. Refining the shared grid to 0.05 seconds
produces only small TRAIN changes. `fractional_per_track_evaluation.json` then
runs the actual historical diagnostic: fixed identity, independent per-track
tau in [-5,+5] seconds at 0.25-second nodes, followed by continuous linear
profiling inside the winning interval. It covers both 16-scan TRAIN groups and
both 16-scan validation groups, with both priors and both inherited terminal
points.

At the inherited shared terminal points, fractional timing has post-seal error
of 8.474/9.152 km on first TRAIN, 1.889/1.921 km on second TRAIN, 12.216/12.273
km on the first validation group, and 4.964/5.026 km on the second (Sacramento/
Reno). About 3--10% of fixed tracks select an exact ±5 s boundary, confirming
that this freedom is weakly constrained. The 1.9 km second-TRAIN points do not
transfer to the first validation group, and none supports a sub-kilometre
claim. Held metrics and reference error are calculated only in `finalize.py`
after all fractional files are sealed.

The historical fractional report performed its own local location search over
conditional points. This new diagnostic does **not** reproduce that exposed
search: it evaluates only DS1's frozen paired-run terminal geographic point
union. Its rows therefore isolate the unconstrained timing effect at a common,
TRAIN-selected DS1 trace rather than claim parity with the historical 631 m
number.

The exact 64-scan TEST case remains an explicit input failure for both priors:
`scan-hop-6cd2560365a058bc`, position 48, lacks complete counter-continuity
authority. No row drops, replaces, or works around that recording.

Run `integrate.py` to regenerate the historical row table,
`fractional_per_track_diagnostic.py --case CASE_ID` for each of the four
declared cases, and `finalize.py` to export post-seal JSON/CSV/plot. Tests cover
the TRAIN-only scale selection, deterministic common-tau tie handling, and
four-group fractional artifact coverage.
