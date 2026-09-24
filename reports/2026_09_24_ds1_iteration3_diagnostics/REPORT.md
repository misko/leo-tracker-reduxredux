# DS1 iteration-3 rate and basin diagnostic

This report analyzes the completed, TRAIN-only iteration-3 artifact
`../2026_09_24_ds1_joint_rate_search/iteration3-results.json`
(`sha256:7d08cc2303bd942c94ac9dd73e56da49f71736b94c9d49ae9a2690489ffe4e1e`).
No reference coordinate or reference-derived mask was used in the analysis
that produces the inference findings below.  The final post-seal subsection is
explicitly separated and only explains the already-completed results.

## Findings

All four selected fits reached the screening cap of 30 L-BFGS-B iterations and
reported `converged: false`.  The fixed-winner, reference-free diagnostic
re-ran the same all-qualified hard support at caps 30, 120, and 300 without
changing a geographic/tau selection.  Every fit converged at 161--189
iterations.  A cap of 120 still did not converge.  Therefore iteration 3's
published screen ranking includes optimization truncation; it should not be
treated as a fully profiled rate objective.

| TRAIN group / seed | tracks / NORADs | 30->300 rate RMS (s/h) | 30->300 objective change | 30->300 boundaries | selected tau and tau margin | best other geographic margin |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 20260921_00 Reno | 476 / 109 | 0.00662 | +0.000184 | 1->1 | -1.25; +0.000106 to -1.50 | 0.0000287 |
| 20260921_00 Sacramento | 476 / 109 | 0.00664 | +0.000311 | 1->1 | -1.25; +0.0000526 to -1.00 | 0.0000322 |
| 20260921_16 Reno | 298 / 130 | 0.01042 | +0.002501 | 1->1 | -0.75; +0.000531 to -1.00 | 0.000243 |
| 20260921_16 Sacramento | 298 / 129 | 0.01031 | +0.001597 | 2->3 | -1.25; +0.006179 to -1.50 | 0.000451 |

Margins are differences in the published 30-iteration screening selection
objective.  The timing runner-up is the best point at a different tau; the
geographic runner-up is the best point at any different offset.  Every selected
tau is an edge of its three-value stencil.  This leaves a one-sided timing
direction untested at every winner.  The two 00 seeds both meet at -1.25 s,
but it is the upper edge for Reno and lower edge for Sacramento.  The 16 Reno
winner is at its upper edge (-0.75 s), while the 16 Sacramento winner is at
its upper edge (-1.25 s); the seeds do not share a timing/location basin.

The rate model has real support, but its weakest sources are not equally
identified.  In the 00 group, the median NORAD has 3 associated tracks and
27/109 NORADs have one track; in the 16 group the median is 2 and 47--48/129--130
have one.  After per-track CFO profiling, the local data-curvature proxy gives
11--12 weak-prior-dominated sources in 16 versus 6--7 in 00.  The result is
consistent with the larger 16 cap-sensitivity and more boundary contact,
rather than evidence that a common set of rate estimates pins down 16.

Boundary contact is persistent.  At the winners, 00 has one rate at the
±0.25 s/h bound; 16 has one (Reno) or two (Sacramento).  Across its screen,
00 has one bound at 83.3--89.6% of points and two at the remainder.  The 16
screens have one to four bounds: Reno 1/2/3/4 at 36.8/54.9/5.6/2.8% of points,
Sacramento 1/2/3 at 18.8/68.8/12.5%.  These rates are constrained fits, not
unbounded observations of a physical phase-rate distribution.

Association counts do not explain the 00 location discrepancy through a
wholesale identity change.  Its two winners share all 476 tracks and 473
(99.37%) candidate assignments; their rate vectors overlap on 108 NORADs with
0.00444 s/h RMS difference.  Their selected positions are 0.939 km apart.
For 16, the winners still share all 298 tracks but only 288 (96.64%) candidate
assignments; the 125 overlapping rate estimates differ by 0.02416 s/h RMS and
the positions are 2.883 km apart.  The 16 seed split is thus coupled to a
sparser, less stable rate/association fit, even though most identities remain
the same.

The cached screening loss is too coarse to decide many local comparisons.  The
one-winner exact audits differed from the surrogate loss by 0.00434, 0.00464,
0.00225, and 0.00242 for 00 Reno, 00 Sacramento, 16 Reno, and 16 Sacramento.
Those discrepancies exceed the nearest-location objective margin by about
151x, 144x, 9x, and 5x respectively.  They also exceed the tau margin by
41x, 88x, 4x, and 0.39x.  Exact SGP4 replay itself passed at every winner
(maximum absolute replay mismatch below 5.9e-05 Hz); the limitation is using
the cache surrogate to rank candidates whose score differences are much
smaller than its observed loss discrepancy.

## Why the observed outcomes differ

The reference-free evidence says 00 has a narrow agreement between priors in
association and rate estimates but a locally flat, surrogate-dominated
geographic/timing surface.  Both seeds stop at the shared stencil edge,
roughly one kilometre apart.  There is no reference-free basis to call the
result a settled geographic optimum.

The 16 evidence is worse conditioned for a single local answer: 37--38% fewer
tracks, only two tracks per NORAD at the median, roughly twice the cross-seed
rate disagreement, more bound hits, a 2.883 km seed split, and a Reno timing
edge that lies outside the sole shared tau value.  These are sufficient to
explain why its seeds diverge without invoking truth information.

Post-seal comparison is explanatory only.  Against the withheld reference,
the 00 outputs are 4.260 km (Reno) and 4.204 km (Sacramento), so their
approximately 4.2 km residual is a shared systematic basin error rather than
a seed-specific failure.  The 16 outputs are 0.635 km and 2.949 km, matching
the reference-free seed-instability diagnosis.  These values must not select
the next method, tau range, candidate, or regularization.

## Predeclared iteration-5 protocol

Run a reference-free, TRAIN-only iteration 5 with the following fixed policy:

1. Replace the three-point seed-centered tau stencil with the common,
   symmetric `{-2.25, -2.00, ..., -0.25}` s grid (0.25 s spacing) for every
   seed.  This contains every iteration-3 stencil and tests both sides of the
   common -1.25 s edge without looking at the reference.
2. Use a 300-iteration rate solve at every screened point; reject a run that
   does not converge instead of ranking its truncated objective.  Keep the
   current ±0.25 s/h guard but report the bound identities and the
   per-NORAD support count.
3. From the converged cache screen, preselect 12 candidates per seed: the
   cache winner in each of the nine tau cells, plus three cache-ranked spatial
   candidates at least 0.78125 km from every already-selected candidate.
   Exact SGP4-fit and re-rank all 12 using the exact capped loss.  This
   directly addresses the measured surrogate/margin mismatch while keeping
   the exact work bounded to 48 finalists.
4. Publish the exact winner and the best candidate at every tau cell, then
   measure agreement between the independently seeded estimates.  Treat a
   tau-edge winner, nonconvergence, more than one bound per 100 NORADs, or a
   seed separation above 0.78125 km as an unresolved-basin result rather than
   a position estimate to tune against post-seal error.

This removes the two measured sources of systematic selection bias: a
truncated rate profile and cache-only selection in a surface whose local
margins are below cache-to-exact discrepancy.  The protocol is completely
specified from sealed RF artifacts and iteration-3 diagnostics; it does not
use post-seal coordinates or errors for fitting or selection.

## Artifacts

- `convergence_diagnostic.py` is the executable fixed-winner experiment.
- `convergence-diagnostic.json` records its immutable inputs, bindings, and
  machine-readable results.
- `diagnostic-summary.json` is a compact index of the metrics in this report.
