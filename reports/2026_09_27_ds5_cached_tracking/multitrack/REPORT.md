# Causal multi-track bank result

## Decision

Reject this three-track strategy without retuning or another data replay. It
matches only 118 of 129 independent top-reference positives and costs more CPU
than blind acquisition. It fails the frozen scientific and performance gates.
No old-development, holdout, ARM, RF, or production run follows.

## Scientific result

| Cohort | Reference positives | Identity matches | Lost | Additional | Cache hits |
|---|---:|---:|---:|---:|---:|
| 2.5 Msps | 62 | 57 | 5 | 5 | 24 |
| 5 Msps | 67 | 61 | 6 | 6 | 34 |
| All | 129 | 118 | 11 | 11 | 58 |

Candidate and reference positive counts are both 129, but this count equality
hides 11 different timing/CFO identities. Every mismatch occurs on a cache-hit
row. All 198 blind fallback top results exactly equal the independent packed
reference, so fallback does not cause the losses.

The strategy attempts a cache bank on 161 receiver-visits and performs 264
full-aperture checks. Two visits accept more than one track. On one mismatched
5 Msps visit, an accepted alternative check matches the reference identity,
but the preregistered largest-current-margin rule selects the competing track.
The other ten mismatches have no checked track within the unchanged two-
microsecond/eight-kilohertz reference bounds. This is diagnostic evidence; the
reference cannot be used to change selection after the run.

The bank reaches its capacity of three tracks. After each failed bank it runs a
top-three blind fallback, producing 594 charged window confirmations across
198 blind calls. Those lower fitted observations are strategy-owned and causal,
but they do not make a lower window the detector output: the blind rank-1
observation remains authoritative for that visit.

All 24 isolated controls retain their decisions: eight pilot controls are
positive and eight noise plus eight tone controls are negative for both
candidate and reference. Because every control starts cold, this verifies only
the top-three acquisition path.

## Cost result

| Rate | Reference CPU | Strategy CPU | CPU speedup | Reference matches |
|---|---:|---:|---:|---:|
| 2.5 Msps | 283.749 ms | 385.694 ms | 0.736x | 57/62 |
| 5 Msps | 620.542 ms | 775.542 ms | 0.800x | 61/67 |
| All | 904.291 ms | 1161.236 ms | 0.779x | 118/129 |

A ratio below one means the strategy is slower. It consumes 28.4% more CPU
than the packed maximum-one blind reference. The frozen performance gate
required at least the prior full-aperture V6 replay's 1.797x overall speedup and
at least 1x at each rate. Neither rate passes even the no-regression bound.

The cost includes every full-aperture cache check, bank bookkeeping, natural-
stride selected-window and fallback processing, and every actual maximum-three
fallback. File loading and input hashing are excluded from both sides. Medians
of three timed repetitions after one warmup are summed by receiver-visit, with
reference-first order alternated by visit and receiver.

## Interpretation

Keeping competing fitted tracks does not solve the top-identity problem under
this causal policy. It sometimes preserves a reference-compatible alternative,
but the strategy has no causal basis to prefer that weaker current margin over
the selected track. Choosing it from the independent comparator would be
reference feeding. The bank also reduces cache hits from the prior single-track
new-data replay while increasing fallback work because it checks all tracks
and confirms three blind windows.

Discovery association deliberately uses the strict scientific identity bound,
rather than the wider tracking-learning envelope. That prevents merging
distinct hypotheses but can split one quickly moving trajectory into another
track. Changing that association or selection rule would be a new experiment,
not a repair to this frozen result.

The result provides no path to a 10x whole-stream gain. It does establish that
multiple causal hypotheses alone do not disambiguate which fresh positive is
the independent detector's top identity.

## Provenance

- New-data manifest SHA-256:
  `b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845`
- Frozen design SHA-256:
  `7e422de799770e6927b47568ef1c1482bb4f0b1cd1e0072fff6930b21d58723b`
- Bank implementation SHA-256:
  `50efbc4dd4b7b1e6f6882b6c74e2917b412226861a8a26926bf7a89629727e24`
- Runner SHA-256:
  `01b3e2ce31cd2215e1ff9c3379af1a918e3606d6ffa623c34643dd4d39e8b9c2`
- FP64 V4 native binary SHA-256:
  `8cdc21362e8cb98a21550b0ba2024674881ca106706d9c799b33e5d4f5a7e614`
- Row-level results SHA-256:
  `e434f0e6c7ca3894ffde4ef40d2db7051433e42e4e159183656eab11b9f53dff`

This is server development evidence. The independent blind top is a detector
reference rather than physical truth, and additional positives are
unadjudicated rather than false positives.
