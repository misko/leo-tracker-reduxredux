# Exact full-data nomination after the moment failure

Streamlining the full-data nomination reduced broad discovery and cold ranking by about **12 ms** on DS30-0016 and **18 ms** on the northern wrong-region simulation. Both replays kept the ordered candidates, all cold scores, nominee diagnostics, the initial `c = 0` gate, and the full fitted-`c` refinement of the selected branch. The temporal-moment method remains rejected after the dense DS30-0008 comparison.

## Isolate the dense-case discrepancy

The completed DS30-0008 replays used identical saved detections and the same geographic offer. Temporal moments changed **12 of 111** selected initial track owners and kept their discrete aliases. The initial full-data gate retained 2,905 points versus 3,236 in the control. Each published arm went from 4,472 to 4,365 owned observations and from 26 to 25 satellites. Fitted horizontal error rose from about 1.51 to 2.92 km while solver RF RMS moved from 148.44 to 147.42 Hz. [Earlier time-moment prototype](solver-track-moments.md) · [Physical reference](../location-audit/README.md)

The follow-up replayed the 12 changed components at the centre and four corners of their original offer with a fixed zero radio and phase state. Each of the 60 nominations examined the full causal catalogue. It substituted one term at a time. The test used saved detections and rebuilt one frozen causal sky. It did not repeat either complete solve.

| Substitution at the fixed anchors | Changed ungated nominees |
|---|---:|
| Quadratic time interpolation of Doppler with original full visibility and profile | 1 of 60 |
| Node-only visibility with original full Doppler and profile | 0 of 60 |
| Moment algebra versus dense profiling of the same interpolated Doppler and same node visibility | 0 of 60 |

There were zero visibility-mask differences and zero discrete alias differences across the 60 comparisons. The compressed moment algebra and dense evaluation of the same interpolant differed by at most 8.94 × 10⁻⁸ profile score units. The Doppler interpolation by itself changed a southwest-corner nomination on channel 7 from NORAD 63592 to 64194. The saved final branch disagreement for that track had those labels in reverse order. The fixed-state audit demonstrates a direct interpolation failure and leaves the downstream effects of learned phase and hardware states unresolved. [Audit runner](solver_streamed_nomination_trial.py)

The nomination routine consumes the lowest visible profile cost regardless of its preliminary binary noise gate. The gate still participates in ordinary association and final acceptance. Dropping full-candidate noise and residual diagnostics within the two nomination-only discovery routes can therefore preserve their choice when the complete costs, aliases and visibility remain exact.

## Full-time candidate ranking

The prototype keeps every observation and catalogue entry, full-time horizon checks, and the original order of alias, bias and cost reductions. Each track retains the original Gaussian bias likelihood and the first catalogue index on a tie. It replays the stock profile for non-diagonal whitening. The unweighted residual RMS and noise diagnostic are computed only for the selected row. Existing later acceptance and fitting operations use their unmodified full-data code. The binding is scoped to the two discovery methods that pass their results to the nomination consumer. [Prototype](../../../tools/pipeline_eval/variants/algo08_streamed_nomination.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_streamed_nomination.py)

Each saved replay starts from a fresh exact scan context, then runs broad discovery and exact cold ranking, including the previously validated reuse of identical association calls in both modes. Two pairs reverse execution order. The timing covers ranking only. Both initial calibration refinements run after each timed rank as an equivalence check. [Trial runner](solver_streamed_nomination_trial.py) · [Identical-call reuse](solver-discovery.md)

| Saved input | Control rank CPU (s) | Streamed rank CPU (s) | Candidate profiles / omitted nonwinner residual diagnostics per rank |
|---|---:|---:|---:|
| DS30-0016 | 0.254, 0.245 | 0.236, 0.239 | 69,552 / 69,504 |
| North far | 0.501, 0.507 | 0.482, 0.492 | 376,560 / 376,320 |

Exact score arrays and aliases also matched in the component tests for row-major and column-major input, tied candidates, empty visible sets and values within one float of an alias boundary. These small saved-input controls stop after initial refinement. They establish local equivalence at the tested boundary. The savings are small, and this trial supplies no complete publication timing or dense-case qualification for the exact-only path.
