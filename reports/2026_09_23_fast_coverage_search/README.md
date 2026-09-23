# Fast multiresolution CF510 coverage search

## Predeclared benchmark

This benchmark compares certified fixed-grid top-K searches with an adaptive
multiresolution heuristic for `scan-fw-cf510316ae7f05d5`. It uses ten selected
tracks from the scan, containing 372 unique observation IDs, with strict causal
catalogue authority and Sacramento, Reno, and Denver prior circles of 350, 750,
and 2,500 km. Its results describe those ten tracks, not the entire scan.

**Latest initialization policy:** future searches require the starting position
to be within 500 km and must cap the search radius at 500 km. Sacramento and
Reno satisfy the recording's initialization-distance assumption; Reno's
historical 750 km search radius and Denver's 2,500 km radius exceed the new
search cap. Denver remains here only as a measured wide-prior stress test, not
as a supported future initialization. The tables retain the executed radii so
the historical measurements stay reproducible.

The primary cell objective is unique observation coverage, with a maximum of
372. Ties are resolved by the threshold-clipped sum of each track's best
held-out RMS and then stable east/north coordinates. Track count, summed span,
and observation-weighted RMS are reported diagnostics. The partition mask is
frozen per track and independent of position for the primary benchmark.

For each city, the benchmark runs complete coarse grids and a certified exact
top-K search over every declared 50 km grid center. The adaptive search starts
at 200 km and compares fixed basin widths before bounded 25 and 12.5 km
refinement. Threshold 200 Hz is the primary run. Thresholds 500 and 800 Hz are
derived globally only from a complete candidate cache; in a top-K-only output,
they describe the selected finalists and are not global optima.

The 50 km adaptive stage can be compared with the certified 50 km fixed-grid
authority. The finer 25 and 12.5 km stages have no exhaustive oracle. Reported
measurements include evaluated points, preparation time, search time, finalist
recomputation time, finalist coordinates, and candidate IDs. The adaptive
algorithm is a heuristic and is not described as A*, branch-and-bound, or
globally certified.

The previous 50 km regional maps used observer-dependent randomized masks and
serve only as a legacy-parity oracle. They are not the authority for the new
fixed-mask search. Fixed-mode claims require a new fixed exhaustive baseline.

Reference-coordinate distance is evaluated only after search selection and is
never used for scoring, pruning, refinement, basin retention, or tie breaking.

The randomized held-out RMS participates in selecting both catalogue candidates
and spatial cells, so it is a selection score rather than independent final-test
accuracy. At the 200 Hz threshold, a track qualifies when its best per-track RMS
is strictly below 200 Hz; the reported observation coverage then counts both fit
and evaluation observation IDs belonging to qualifying tracks.

## Qualification requirements

Publication requires:

- fixed-mask coordinate invariance and exact score-semantics tests;
- legacy-mode parity against the existing implementation;
- exact exhaustive lattice and adaptive parent/child trace validation;
- no duplicate evaluated coordinates;
- prediction-cache and uncached state equivalence, or an explicit limitation
  if that proof is unavailable;
- measured verification that the standard 209-sample coarse elevation gate
  implies the 1,316-sample broad gate before claiming that geometry reduction;
- source, test, benchmark, trace, and input digests in the artifact manifest.

The final report will be self-contained for verification and rendering. A full
numerical rerun may still require the public stored-track source and causal TLE
archive bound by the copied receipts.

## Results

The reusable prediction bank took about 18--26 seconds to prepare. On the
qualified lazy evaluator, complete 200 km searches took 2.15 seconds for
Sacramento (9 centers), 9.79 seconds for Reno (45), and 105.03 seconds for
Denver (489). The 16-worker exact top-15 Denver 50 km search visited all 7,860
declared centers, fully scored 1,129, safely pruned 6,731, and took 161.45
seconds. The eight-worker Sacramento result exactly matched the serial top 15
and reduced search time from 27.77 to 6.10 seconds. Reno's serial certified
search took 106.05 seconds for 716 centers, of which 81 were fully scored.

Constant-beam-8 refinement missed Sacramento's best basin. Coarse-seeded beam
32 through 12.5 km evaluated 621 Sacramento, 868 Reno, and 1,494 Denver centers.
That control covered all 372 observations in Sacramento and Reno, but its
Denver cell covered 356 observations from nine tracks and remained in an
eastern false basin.

The recommended pipeline first certifies the exact 50 km top 15 and then
refines only those seeds at 25 and 12.5 km. It evaluated another 172, 168, and
169 local centers after the 15 certified seeds and recovered all 372
observations from ten tracks in every region. Its Denver finalist was 18.07 km
from the evaluation-only reference. This local refinement is still a heuristic;
it is not a globally optimal 12.5 km search, and reference distance did not
participate in selection. Matching the selected catalogue trajectories alone
does not establish a calibrated position uncertainty.

The seeded refinement was launched with an inline driver. Its reproduction
bundle is explicitly retrospective: it preserves the exact executed engine
bytes and a reusable equivalent runner, but does not represent that runner as a
pre-run authority. The receipt and executed engine digests are verified by
`qualify.py`.

The spatial step is the spacing between evaluated centers; it is not a position
accuracy or uncertainty. The fine adaptive rows have no exhaustive 12.5 km
authority, so their top-K recall and objective gap are deliberately null. The
completed adaptive runs predate persistence of every evaluated score; their
traces preserve all evaluated coordinates and work per level, while only the
final top 15 retain scores. The report does not fabricate score progression for
those missing intermediate rows.

| City | Prior radius | Selection | Grid step | Observations / tracks | Weighted RMS | Post-selection distance | Search time |
|---|---:|---|---:|---:|---:|---:|---:|
| Sacramento | 350 km | coarse-seeded beam 32 | 12.5 km | 372 / 10 | 104.38 Hz | 5.79 km | 142.50 s |
| Reno | 750 km | coarse-seeded beam 32 | 12.5 km | 372 / 10 | 101.47 Hz | 9.41 km | 196.74 s |
| Denver | 2,500 km | coarse-seeded beam 32 | 12.5 km | 356 / 9 | 114.46 Hz | 3,554.91 km | 365.00 s |
| Sacramento | 350 km | exact-50 top-15 seeded | 12.5 km | 372 / 10 | 104.38 Hz | 5.79 km | 40.10 s |
| Reno | 750 km | exact-50 top-15 seeded | 12.5 km | 372 / 10 | 101.47 Hz | 9.41 km | 37.11 s |
| Denver | 2,500 km | exact-50 top-15 seeded | 12.5 km | 372 / 10 | 102.26 Hz | 18.07 km | 39.15 s |

At Denver, the best cell over the union of all evaluated levels remained the
25 km cell at `(2037.5, 187.5)` km, with the same 356 observations and nine
tracks but a lower clipped RMS sum of 1,170.10 Hz. The final 12.5 km level chose
`(2018.75, 193.75)` km with a clipped sum of 1,191.00 Hz. The progression figure
keeps the current-level and evaluated-union series separate.
