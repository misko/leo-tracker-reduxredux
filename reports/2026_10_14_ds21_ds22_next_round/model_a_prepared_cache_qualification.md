# Prepared-input runtime qualification and completed matrices

Commit `a75b444ff` adds an explicit cache port and a new runtime schema,
`ds21-qualified-abc-prepared-cache-v2`. The original scientific protocols,
models, starts, fitting functions, six-start selectors, and fitted-c 20-second /
600-iteration calls remain unchanged. The new runner's `run` function is AST
identical to the qualified v1 facade except that its preparation-load bound is
five seconds. All **21 component tests passed in 90.85 seconds**; Ruff passed.

The measured need was five DS21-003 v1 failures under an eight-worker fit wave
with concurrent source freezes. Each exhausted the 30-second preparation bound
before creating any optimizer claim. These failed namespaces and receipts are
preserved. A new protocol binds all five zero-call failures, reuses seven
validated completed outcomes, and runs the remaining units through the cache.
No completed scientific call was repeated.

The cache contains exact public `PreparedPositionWindows`,
`PositionObservations`, selected `PositionOrbitBank`, training `TrackingInput`,
partition metadata, prior, and clock nodes. Held observations are not
serialized. One expensive source qualification or preparation can hold the
shared admission gate at a time; fits never hold that gate. Admission waits are
bounded to 120 seconds. One-time original preparation has an explicit 45-second
runtime amendment; all numerical fit budgets remain unchanged. Source freezes
have 240-second external bounds and qualification has a 450-second bound,
covering both possible admission waits, two original preparation replays, and
the separate audit. A/B/C units retain 90/165-second internal and
105/175-second external TERM limits, followed by five-second KILL grace.

Actual DS21-003 qualification completed in **52.177 seconds**, after an
11.217-second genuine source freeze. Cache building took **14.039 seconds**
with zero optimizer, objective, or predictor calls. A fresh original replay
matched all prepared arrays, candidate/window identities, bootstrap tracks,
training timing/probes, partition metadata, prior, selected orbit arrays, and
clock nodes exactly. Identical fixed states then produced exactly equal B/C
objectives, full gradients, nuisance gradients, and posterior fields for all,
low, and high views. That separate audit made **12 objective calls and 12 orbit
predictions, zero optimizer calls**. Its states and bindings are recorded in
the source-bound equivalence receipt; no reference was consulted.

Eighteen simultaneous read-only cache qualifications all passed while DS22
workers were active. Cache loading averaged **0.303949 seconds**, maximum
**0.665147 seconds**, within the five-second limit. Authority checks before
loading averaged 0.338032 seconds (maximum 0.577072); afterward they averaged
0.285805 seconds (maximum 0.445080). These readers made no objective, predictor,
or optimizer calls.

The five previously zero-call DS21-003 units completed in the new namespace:
A-4 26.060 seconds, A-5 18.853, B-high 25.044, C-low 63.103, C-high 69.399.
The old failures are still bound in the new protocol. Together with seven
validated metadata reuses, these sealed all twelve outcomes before evaluation.
The matrix has 24 new and 28 reused calls; A-3's previously retained
nonstationary low stage accounts for the two omitted downstream calls.

Three matrices completed through this runtime work:

| Scientific arm and case | A all | B all | B low | B high | C all | C low | C high |
|---|---:|---:|---:|---:|---:|---:|---:|
| original-v2 DS21-003 | 2.601105 | 2.729078 | 5.432679 | 1.181486 | 1.956673 | 3.838802 | 0.850487 |
| original-v2 DS21-007 | 2.670229 | 5.043613 | 6.619315 | 3.120689 | 3.523663 | 3.738163 | 4.324831 |
| coverage-v1 DS21-005 | 1.426279 | 2.213563 | 3.607561 | 1.300717 | 2.387111 | 1.373228 | 1.149257 |

Values are post-seal position errors in kilometres. These are distinct cases
and arms, not a matched before/after improvement claim. Frequency objectives
and RMS values remain separate in their scientific call receipts. Low/high
views retain the original shared CH1–8 candidate bank and physical-start
qualification; they do not constitute independent half-only initialization.

Runtime namespaces under this report's `local` directory are
`model-a-pipeline-before-003-cached-v2`,
`model-a-pipeline-before-007-cached-v2`, and
`model-a-pipeline-coverage-005-v1`. Each has `terminal.json` binding all twelve
unit outcomes, and `development-errors.json` binding that terminal. The
accompanying JSON binds the exact protocols, scientific parents, qualification
receipts, failed attempts, worker-wave receipts, and completed evaluations.
Eight additional ready parents have passed cache-v2 source freezes; their
qualification, original seed initialization, and bounded model matrices are
being advanced separately. No existing frozen runner was edited.
