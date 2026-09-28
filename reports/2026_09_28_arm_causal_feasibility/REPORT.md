# Prior-window search-region feasibility

This is a retrospective feasibility screen over the frozen 704-dwell original
baseline, not an implemented local detector, recovered GLRT measurement, or
ARM benchmark. The baseline supplies candidate coordinates and scores inside
each proposed region, which a real implementation would have to discover and
score from IQ. Results are optimistic design evidence, not a guaranteed bound.

Each receiver starts independently in each dwell. Every Kth window receives a
full search. Other windows use only candidates retained in the preceding
window, shifted by the 10 ms advance. A candidate missed by the proposed
region cannot seed the following window. An empty seed set causes a full
search. Both positive and negative retained candidates can seed. Nothing is
carried across the noncontiguous selected dwells. All 20 ms windows remain in
the accounting; this policy does not stop after a dwell confirmation.

The grid examines K = 2, 4, 8, 16, epoch radii 2, 8, 32, 128 samples and CFO
radii 2, 8, 20 kHz. Selection below is retrospective on this same cohort and
therefore requires held-out validation before tuning a detector.

## 2.5 MS/s findings

| Setting | Original hits inside proposed regions | Windows needing full search | Ideal search-cost reduction if local work were free |
| --- | ---: | ---: | ---: |
| K=2, radius 8 samples / 8 kHz | 4,150 / 4,573 (90.75%) | 1,824 / 3,344 (54.55%) | 1.83× |
| K=8, radius 128 samples / 20 kHz | 3,762 / 4,573 (82.27%) | 1,260 / 3,344 (37.68%) | 2.65× |

These rows use the rounded epoch-grid period. The native frame offsets use
rounded multiples of the physical period, so the exact transform for a local
implementation needs explicit frame indexing. A second calculation with the
physical period (rate / 750) is retained in `results.json`: its smallest 90%
region uses radius 2 and covers 4,148 hits, while the 80% row is unchanged.
The narrow-region percentages are coordinate-model sensitive; the conclusion
that refresh/fallback work dominates is unchanged. The sensitivity run is
`integer-period-results.json`; neither model substitutes for an IQ experiment.

Using the prior measured mean of 33.913 CPU seconds per dual-RX dwell only as
a cost estimate, 54.55% full-window work alone costs about 18.5 s/dwell. That
is roughly 257 times the 72 ms/dwell budget for 40% headroom. This simple
refresh policy is therefore not a promising route to that target. Even the
80% setting is far short before charging any local confirmation work.

Next algorithm work needs cheap discovery on windows without usable seeds,
and much rarer exhaustive fallback, rather than merely replacing alternate
full searches with tracked local searches. Any candidate implementation must
measure actual individual-hit recovery and CPU on saved IQ; this screen cannot
establish either.

`test_coverage.py` checks wrapped timing translation, CFO exclusion, and that
missed candidates cannot appear in subsequent seed state. Input SHA256 is
recorded in both result files. Terra's independent review is in `REVIEW.md`.
