# Why frozen A misses proposal support

This is a read-only diagnostic replay of frozen A over all five original
recordings. It runs the existing automatic extraction, then the existing
65-node absolute timing grid (-8 to +8 s at 0.25 s spacing), with exact orbital
projection and the original observed RF. It performs no physical optimizer or
refit and changes no frozen model/result. Window bounds and candidate hypotheses
are evaluation labels applied after whole-recording extraction, never runtime
inputs to extraction or its full-bank profiles.

The decisive failures are global arc selection, thresholded subsampling and
the final candidate rank cap. A new quadratic extractor is not required to
demonstrate them. Parent iteration 2 can test its candidate-wide full-point
coordinate profile without adding extraction machinery.

## Whole-challenge proposal coverage

Frozen A fits line arcs within 24 s windows, retains at least eight points over
at least six seconds, sorts all deduplicated arcs by descending point count,
and keeps only the first 48 across the entire recording. In these sources,
the shortest selected arc has 17 or 18 points. A genuine lower-density arc can
therefore lose all access to timing proposals.

Replaying with a diagnostic cap of 512 exhausts each pool: only 385–427
deduplicated arcs exist, so the larger cap never binds. This is a diagnostic
counterfactual, not a newly accepted model. Coverage is the unique union of
arc-member rows inside each fixed window; overlapping arcs do not multiply
the counts.

| Region | Source | All window rows | Covered by selected 48 arcs | Covered by complete linear-arc pool |
| --- | --- | ---: | ---: | ---: |
| 001 | S01 | 86 | 46 | 85 |
| 002 | S01 | 35 | 13 | 32 |
| 003 | S01 | 27 | 0 | 27 |
| 004 | S02 | 44 | 36 | 43 |
| 005 | S02 | 33 | 0 | 29 |
| 006 | S02 | 72 | 29 | 72 |
| 007 | S03 | 54 | 0 | 46 |
| 008 | S03 | 50 | 0 | 43 |
| 009 | S03 | 34 | 0 | 29 |
| 010 | S04 | 46 | 38 | 46 |
| 011 | S04 | 43 | 29 | 38 |
| 012 | S04 | 66 | 32 | 65 |
| 013 | S05 | 28 | 19 | 28 |
| 014 | S05 | 39 | 2 | 33 |
| 015 | S05 | 36 | 30 | 30 |
| Total | Five recordings | 693 | 274 (39.54%) | 646 (93.22%) |

The complete pools have 411, 403, 415, 385 and 427 arcs for S01–S05. Regions
003, 005, 007, 008 and 009 have no selected-arc overlap. A satellite can still
be proposed through another lane or time interval; that does not mean the
window itself contributed proposal evidence.

## Region 008: a phase that exists but is excluded before profiling

The S03 48-arc pool contains zero of this window's 50 observations. Its best
window-specific arcs are ranked 85 and 97: each has 15 points, below the
17-point global selection floor. The complete automatic pool covers 43/50
window rows without changing the line model, coherence gate or timing grid.

Under the selected 48 arcs, retained candidate 60127 has gain zero, supporting
arc count zero and rank 24, so it is never proposed. With the complete pool,
the same generic full-bank profile finds candidate 60127 at -1.25 s, gain
4,167.85, 16 supporting arcs and rank 2. It now passes all existing proposal
gates. Its original saved timing was -9.5516 s.

This agrees in phase with the saved target-informed standalone diagnostic:
-1.175 s and 139.02 Hz RMS on 42 selected coherent observations. That selected
42-point result is not an accuracy label for all 50 window observations.
Nevertheless, the automatic complete-pool replay establishes that the missed
phase is available inside the existing candidate bank and timing grid.
Curvature, absent bank membership and an unreachable timing interval are not
needed to explain this particular omission.

## Region 013: subsampling changes a passing arc into a failing arc

The S05 selected arcs cover 19/28 window rows. At candidate 66854's saved
standalone phase -1.50 s, the selected rank-14 arc has 22 points spanning
46.628–62.251 s, of which 18 lie inside the window. Of its full 22 points,
17 are visible and have absolute residual below 375 Hz: 77.27%, which passes
A's 70% coherence requirement. But A profiles only 16 evenly spaced samples
from that arc. Eleven of those 16 pass: **68.75%, which fails the gate**.
The same physical phase and same arc therefore become ineligible solely
because of deterministic subsampling.

The other relevant selected arc, rank 13, spans 54.439–74.331 s, with only
seven window rows. It genuinely fails the full-arc requirement (15/22), and
its 16-point sample also fails (10/16). No selected arc reaches 70% under
A's actual sampled scoring anywhere in the existing timing grid, so 66854
gets gain zero and rank 27 despite its original +5.1632 s timing being poor.

The excluded rank-68 and rank-77 arcs have 16 points each and pass at -1.50 s
with 14/16 and 12/16 coherent points. Using all automatic arcs produces
candidate 66854 at -1.50 s with gain 960.84 and four supporting arcs. However,
it ranks **11th**, so A's additional top-eight candidate cap still drops it.
Simply enlarging the arc cap would not fully fix this example.

The saved 236.94 Hz standalone RMS uses a 24-point `continuity_1` selection.
The same phase scores 309.59 Hz on all 27 originally unassociated points.
Neither number is an all-28-window success rate, and the saved forward/reverse
timing-only RMS on the selected segment is 465.55/379.05 Hz. Identifying the
missed phase therefore does not establish robust recovery or temporal transfer.
Exact per-arc phase projections are persisted in
`arc_diagnostics_selected_phase.json`.

## Other constraints that remain

The enlarged pool makes S01 candidate 69333 at +2.50 s eligible (rank 7,
gain 947.02), whereas the selected pool gave gain zero. It does not solve every
case: for region 005, the two diagnostic candidates rank 13 and 26 after
enlarging the pool; several S04 hypotheses still have zero or weak coherent
support. The original limited timing interval can also exclude large-shift
solutions. Those are separate issues from the demonstrated cap/subsampling
failures.

Two named diagnostic hypotheses are absent from their fixed final banks:
69433 for S01 region 002 and 57864 for S05 region 014. The S01 saved original
46-candidate timing dictionary explicitly lacks 69433. No fixed-bank timing
method can test those exact identities; catalogue expansion needs a separately
labelled experiment. The hypotheses themselves remain unverified identities.

The complete-pool arc gains sum improvements over potentially overlapping
arcs and clip losses to zero. They are proposal scores, not exact global NLL
gains and not evidence of accepted recovery. Candidate-wide scoring must debit
lost support outside a window and retain the exact timing prior and shared
point-mixture score. The parent's iteration-2 full-point coordinate profile
is intended to test that directly without any of A's three selection gates.

## Reproduction and checks

`arc_diagnostics.py` restores saved original observations, bank order, position,
calibration and timing through public numerical contracts. S02–S05 reuse saved
baseline correction and orbit-bank exports; S01 replays the original through
the shared public context harness. Each source extraction is bounded to 45 s;
the observed total per source, including profiles and any context replay, is
2.35–24.47 s. No RF collection, physical fit or held-score tuning occurs.

Five component tests pass: unique overlap accounting, unchanged missing-row
denominators, alias-crossing extraction, held-CFO extraction invariance, and
the exact 11/16-fails versus 12/16-passes coherence boundary. The two boundary
cases use separate tests. The frozen A source and all previous scientific
fixtures/results remain unchanged.
