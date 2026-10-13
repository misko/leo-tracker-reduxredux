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

The current assigned investigation separates optimizer failure from objective
mis-specification on DS21-039. It replays the original objective and profiles the
unchanged all-band model at each training-selected full/half-band position.
Changing only position in original physical starts preserves calibration,
satellite timing and receiver ambiguity initialization for a matched comparison.

See the [common progress report](README.md) for evaluation coverage, reference
limitations and the plan for full DS21. No locked evaluation result is claimed.
