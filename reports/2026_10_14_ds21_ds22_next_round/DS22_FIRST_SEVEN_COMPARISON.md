# First seven DS22 development cases: configured-reference comparison

All values below are distances in kilometres to the explicitly pinned configured
station reference, **not verified DS22 position accuracy**. Station continuity
is unconfirmed. No target-success claim is permitted. These are the first seven
available development members in frozen membership order; they are not the full
45-member development set or the 24-member locked set.

All seven original fitted-c A/B/C matrices are sealed. The six new cases were
all sealed before their reference joins began. Each row uses the stationary
minimum-training-objective selection already fixed in that case's seal; no
reference-based candidate, start or model selection was performed. All runs
use the same original model math and fit limits. This is a model/view comparison,
not a before/after improvement claim.

| DS22 | A CH1–8 | B CH1–8 | B CH1–4 | B CH5–8 | C CH1–8 | C CH1–4 | C CH5–8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 001 | 3.750 | 0.785 | 3.555 | 6.440 | 21.266 | 23.645 | 12.163 |
| 003 | 1.903 | 1.819 | 2.809 | 2.829 | 2.828 | 4.132 | 1.643 |
| 017 | 1.532 | 3.059 | 2.463 | 1.638 | 3.769 | 3.303 | 2.042 |
| 019 | 107.371 | 113.239 | 166.428 | 154.377 | 142.114 | 203.397 | 214.751 |
| 029 | 3.296 | 0.841 | 4.087 | 2.133 | 2.392 | 5.988 | 0.796 |
| 031 | 0.168 | 0.510 | 1.027 | 3.018 | 1.169 | 2.257 | 5.790 |
| 033 | 1.793 | 1.478 | 0.412 | 1.927 | 1.975 | 1.090 | 3.424 |
| Median | 1.903 | 1.478 | 2.809 | 2.829 | 2.828 | 4.132 | 3.424 |
| Count within 1 km of configured reference | 1/7 | 3/7 | 1/7 | 0/7 | 0/7 | 0/7 | 1/7 |

The low/high columns share discovery, candidate unions and initial proposals;
C also inherits receiver lifts from the full-channel initialization. They are
conditional half-view controls, not independent four-channel pipelines. A's
dependent low/high path stages are not standalone half models and are not
reported as such.

B combined is no farther from the configured reference than both of its own
conditional halves on 5/7 cases; exceptions are 017 and 033. C combined meets
that relative comparison on 2/7 cases (019 and 031). C is farther than B on all
seven combined-view comparisons. The C-specific 001 degradation therefore is
not the only C-versus-B deficit, although its magnitude is unusually large.

Case 019 produces distant solutions in every model and view. This motivates
checking shared discovery geography, candidate support and common data/timing
authority, while retaining reference uncertainty. It does not by itself prove
a candidate mismatch or clock defect. Case 001 separates the model issue more
clearly: B and C consume the same shared candidate pool and physical proposal
authority, yet their combined solutions differ substantially. Native branch
likelihood, receiver ambiguity, basin selection and timing parameterization
remain hypotheses to distinguish with controlled diagnostics.

There were 375 actual model optimizer calls, 356 stationary. Counts by case are
001 51/54, 003 49/54, 017 53/54, 019 53/54, 029 49/52, 031 51/53 and 033 50/54.
The lower totals for 029 and 031 reflect dependent A stages skipped after a
nonstationary predecessor, as prespecified. Nonstationary attempts were retained
and never retried. All 84 units completed, with no model-unit checkpoint or
orchestration failure. Shared host load can affect 20-second convergence limits;
there was no budget relaxation or selective rerun.

The source-bound comparison receipts are under
`local/ds22-configured-comparison-v1/DS22-{001,003,017,019,029,031,033}/`.
Each contains its own model protocol/terminal binding, evaluator digest,
reference source snapshot and explicit `configured-unconfirmed` status.
The reference source is `src/leo/cli/regional_position.py`, SHA-256
`6de071077d8c2fe11a991b665c50edaf728ef9ffd320dca36cfedc44ee874bf9`;
the coordinate is 37.84903264307456, -122.4856541910174. It was not substituted
for the separate Sacramento search prior or supplied to any optimizer.

The first independent DS22-001 lower/upper discoveries have also completed:
100 points each on slice 0, in 130.008/122.149 seconds. Their training evidence
matches the corresponding conditional halves exactly, but their point scores,
candidate selections and geographic proposals were computed independently.
Their downstream B/C seeds and models are not yet implemented or evaluated;
the table above therefore must not be represented as the completed independent
half-channel acceptance test.
