# Cross-dwell CFO proposal feasibility and real-time architecture review

## Result

The existing causal current-IQ experiment is the relevant evidence for a
same-channel warm start. Its `Prior CFO + fallback` mode used a prior fresh
confirmation, expired it after three seconds, searched within +/-20 kHz, and
reran the dwell blind when the local attempt failed. It recovered **904/1,154
standard individual GLRT hits (78.3%)** on the chronological 28-dwell DS7
development smoke cohort, including **562/761 (73.9%)** at 2.5 MS/s. It ran
11 local routes, 13 cold blind routes and four local attempts that reran blind.
Its speedup was only 1.11x. This is actual current-IQ recovery, but neither a
real-time ARM measurement nor full-search hit preservation.

The new calculations below are narrower in scientific authority. They seed a
frequency bank from completed **standard** GLRT positives, then compare it to
later standard positives. They execute no current IQ analysis or GLRT and are
therefore proposal feasibility only, never recovery. The sources are standard
baseline comparisons, not the reduced native detector.

| Input | Standard hits | Cold-start hits | Last-prior conditional / full-denominator coverage | Bounded-drift conditional / full-denominator coverage |
|---|---:|---:|---:|---:|
| 28-dwell chronological smoke | 1,154 | 469 | 662/685 = 96.64% / 57.37% | 378/399 = 94.74% / 32.76% |
| 704-dwell stratified stress | 19,581 | 9,171 | 695/9,224 = 7.53% / 3.55% | 25/1,270 = 1.97% / 0.13% |

The chronological smoke has same-key gaps of 0.120--1.322 s (median 0.281 s).
The stratified cohort has 37.143--262.683 s gaps and is a sparse-history stress
test, not a next-dwell test. Cold-start hits are in every full denominator and
must enter a blind path; excluding them is what makes conditional coverage look
high.

The all-pairs two-history bank is intentionally impractical: on the
chronological smoke its median is 315 raw / 154 unique frequencies per eligible
dwell, with a maximum of 2,499 / 1,677. The bounded causal drift bank restricts
this to one prediction per unique latest seed after a fixed 20 kHz nearest
older-history gate. Its median is 11 frequencies (p95 30, maximum 43) on the
chronological smoke. It is an actionable causal predictor shape, but its
oracle-seeded coverage and cold-start burden do not establish that it is cheap
or scientifically sufficient.

## Method and limits

History is keyed by session, channel, edge, receiver and sample rate. It is
sorted by sample-start counter; each prediction may use only earlier records
with that key. Current-dwell candidates never choose a history seed or tune the
20 kHz gate. The bounded-drift predictor associates each unique latest prior
frequency with the nearest older prior frequency before current IQ is observed,
keeps it only within 20 kHz, and linearly extrapolates one prediction.

The script carries `actual_lo_frequency_hz + actual_if_offset_hz` as an
unverified metadata reference hypothesis. Standard acquisition does not consume
those fields. Every eligible pair in these inputs has zero metadata delta, so
the hypothesis changes none of the reported values.

`summary.json` records exact source hashes, inputs, bank sizes, gap bounds,
cold-start accounting and commands. Reproduce with:

```sh
.venv/bin/python reports/2026_09_29_arm_dwell_prediction/analyze.py
.venv/bin/python -m pytest -q reports/2026_09_29_arm_dwell_prediction/test_analyze.py
```

The tests cover LO-hypothesis arithmetic, absolute-frequency extrapolation,
nearest-history gating, and inclusion of cold starts in the prospective full
denominator. They do not validate RF continuity or recovery.

## Architectural priorities

One PLUTO+ analysis core has a 72 ms CPU budget per 120 ms dwell for 40%
headroom. The lag-restricted prototype costs 7.377 s/dwell: 988 ms proposal,
416 ms restricted coarse search, 3,817 ms fine FFT, 1,454 ms conditioning and
572 ms scoring. These independently measured stages must not have their
speedups multiplied.

1. Build a two-resolution pilot-lag screen: decimate/integrate lag products
   into a matched pilot-structure stream, rank timing regions, then refine only
   retained regions with raw lag samples. Its measured 988 ms proposal requires
   a ceiling around 8--10 ms. Scientific risk is loss of weak or multipath
   peaks; final evaluation must use current-IQ GLRT recovery and unmatched-hit
   counts.
2. Replace per-candidate fine FFT with shared or batched pilot sufficient
   statistics and a narrow frequency bank. The present 3,817 ms fine FFT needs
   to fall to roughly 10--15 ms. Residual-frequency boundary cases require a
   bounded full-refinement fallback; coarse-search optimization alone cannot
   meet the budget.
3. Batch or further reduce final GLRT work. Direct CI16 scoring is 1.56 ms per
   call: retrospective standard-positive scores already use 46.7 ms/dwell,
   while all 176 scores use 274 ms. A viable design needs both about 30--40
   calls/dwell and shared/faster scoring near 0.7--0.8 ms/call, leaving time for
   discovery and fallbacks.
4. Reuse overlapping-window statistics, never prior decisions. The 20 ms
   windows overlap by 50%, so incremental sufficient statistics can offer only
   about a 2x arithmetic ceiling by themselves. Existing decision propagation
   every second window recovered 87.2% and still cost 34 s/dwell.
5. Use the cross-dwell prior only as a candidate-ordering hint after the blind
   screen has a cold-start and miss fallback. The existing causal experiment is
   the only current-IQ recovery evidence; the new bounded-drift bank is an
   oracle-seeded design check, not a replacement for discovery.

A proposed 72 ms design budget, not demonstrated feasibility, is screen <=10 ms, frequency refinement
<=15 ms, scoring <=35 ms, and dispatch/fallback <=12 ms. The next saved
corpus prototype should combine the pilot-lag screen and batched frequency
refinement, then report ARM CPU time, proposal-bank cardinality, actual GLRT
calls, one-to-one individual-hit recovery, cold-blind coverage and unmatched
positive entries.
