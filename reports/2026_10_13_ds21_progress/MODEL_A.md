# Model A: sequential band calibration

Status: implemented; five-recording shared-proposal development comparison
complete. This is an interim report; the full DS21 0.5 km target is unmet.

The algorithm fits CH1–4, freezes its physical receiver correction function,
then fits CH5–8 at that position to estimate a high-minus-low shift per receiver.
The final CH1–8 fit uses the learned shifts. It fits all observations jointly at
that final stage; it does not average two estimated positions. The current
comparison uses six shared proposals and selects by final training objective.

| Development recording | CH1–8 error km, fitted `c` |
| --- | ---: |
| DS21-001 | 0.534 |
| DS21-003 | 2.601 |
| DS21-005 | 5.436 |
| DS21-023 | 2.032 |
| DS21-039 | 6.229 |

Median 2.601 km; maximum 6.229 km; 0/5 below 0.5 km; 1/5 below 1 km.
Shared proposals reduced the earlier model's worst-case errors, but this fixed
method still fails the target. A subsequent low-informed joint continuation
did not improve the matched baseline on the two development cases tested, so
that control was not promoted.

The separate [DS21-009 fitted-only comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_009_RESULTS.md)
completed six low/locked-high/final-all paths: all 18 calls were stationary.
The final-training-objective winner, `shape-high`, gives **0.658299 km** for
CH1–8 and fitted c of -631.971642 Hz/GHz. It misses 0.5 km. A is closest among
the three models on this recording; that post-seal observation does not permit
choosing the algorithm by each case's reference error. There are no independently
selected A half-band estimates. A-0's three saved fits were recovered through
a narrow metadata reader, with no refit or numerical-source change. The original
five-case table and its aggregate statistics above are unchanged.

The subsequent [DS21-011 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_011_RESULTS.md)
also completed all 18 sequential calls, all stationary. Its training-selected
`shape-all` final result is **2.491943 km**, with fitted c -406.987881 Hz/GHz
and no reported physical boundary flag. The near-threshold 009 result does not
transfer to this case; A still misses 0.5 km here. No per-case reference-based
choice between A/B/C is made.

The subsequent [DS21-013 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_013_RESULTS.md)
completed all 18 A calls, all stationary, but the training-selected `cold-0`
final result misses severely at **266.839679 km**, with fitted c
82.727343 Hz/GHz and no reported physical boundary flag. Its dependent stages
are not independent half-band estimates. All three models fail severely on
this shared initialization. The post-seal audit finds the configured reference
outside all six original local disks despite being inside the regional prior.
Fixed local refinement cannot recover it; why discovery missed is unresolved.
A reference-blind coverage control must precede further expansion. The historical
five-case statistics are unchanged.

The current assigned investigation separates optimizer failure from objective
mis-specification on DS21-039. It replays the original objective and profiles the
unchanged all-band model at each training-selected full/half-band position.
Changing only position in original physical starts preserves calibration,
satellite timing and receiver ambiguity initialization for a matched comparison.

See the [common progress report](README.md) for evaluation coverage, reference
limitations and the plan for full DS21. No locked evaluation result is claimed.
