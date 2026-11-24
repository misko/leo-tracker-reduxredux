# Single-run evidence for the dense satellite swap

Neither sealed DS30-0008 publication exposes the two-satellite ambiguity on the 11 switched conditional curves. The retrospective join proves that 503 observations kept the same curves and aliases but received another satellite. The single-run curve books provide zero matched incumbent and competitor scores and zero independent held-RF comparisons for those curves. The existing cold-race gate passed both dense runs. There are zero demonstrated avoidable CPU seconds on the evidence available here. [Frozen protocol](0008-prefix-ambiguity-protocol.md) · [Bound audit](measurements/0008-prefix-ambiguity.json.gz) · [Earlier dense substitution](0008-prefix-transfer.md)

## What a single run can observe

The audit first read each publication separately and reconciled all accepted conditional observations with the curve books in both calibration arms. Each dense arm retains 87 nonempty conditional curves, with 3,532 observations on the full-20 input and 3,492 on the hybrid. Candidate IDs and scores are not equivalent evidence. The salvage shortlists log candidate indices for certain rejected tracks, and the support trial lists log a few candidates on proposed subintervals in that earlier context. Eleven final full-20 curves and nine final hybrid curves appeared in those logs. None of the 11 switched curves appeared in either log. The final signed book retains the winning orbit and phase context with array shapes and hashes, but it has no numeric competitor predictions or aligned per-curve candidate score vectors. [Reducer](prefix_ambiguity_0008.py) · [Signed book writer](named_survivor_fit.py)

The live all-catalogue confidence function scores only active families supported on at least two channels of exactly one receiver. It records aggregate track and time counts while dropping track identity, runner-up and score gap. Applying the eligibility predicate to final curve membership covers 22 full-20 curves and 20 hybrid curves. The retrospective overlay shows that only two of the 11 switched curves, containing 73/503 rows, would qualify on either final roster. The other nine contain 430 rows. The true confidence calls run earlier on evolving masks. Their published counters cannot establish which tracks actually received the single-radio profile. [Confidence implementation](lighter_joint_estimator.py)

The 503 switched conditional observations were all part of their respective accepted fits. The existing held receiver choice evaluated first-member acquisition availability and returned unfiltered. It provides no independent held satellite predictions for the late switch. Neither signed book stores a genuinely excluded RF group with both incumbent and competitor predictions and the shared nuisance state fit without that group. The earlier separate dense family-refit experiment documents the same leakage issue for a different pair. [Acquisition evidence](original-dense-intake.md) · [Separate family-refit study](dense-family-refit.md)

## Exact replay of the existing gate

| Sealed analysis | Smallest finalist separation above its required margin | Original cold decision |
|---|---:|---|
| Dense full 20 ms | +58.445 objective units | Winner raced |
| Dense measured-prefix hybrid | +849.942 objective units | Winner raced |
| DS30-0316 same-input publication parity | −78.621 objective units | Ambiguous gap |

The gate compares whole finalist fits at the original cold checkpoint. It reproduces the decisions exactly and gives the hybrid a wider separation despite the post hoc family instability. The 0316 negative control has exact terminal, calibration, objective, owner and eight-PNG parity across its previously measured same-input workers. Its ambiguity flag shows that this whole-race criterion does not distinguish the dense intervention from that benign solver comparison. The negative control establishes parity for those exact runs. It provides no independent certificate of the receiver or orbit assignment. [Cold-race rule](cold_finalist_race.py) · [0316 matched publication](nomination-handoff-0316.md)

## Where time could be saved

| Observed scope in CPU seconds | Dense full 20 ms | Dense hybrid |
|---|---:|---:|
| Cold, including catalogue ranking and original race | 7.722 | 6.863 |
| Remainder of proposal after cold | 6.706 | 6.084 |
| Signed history qualification and both final fits | 2.762 | 2.707 |
| Standard evidence, including the complete grid | 6.570 | 5.885 |
| From solve return to in-worker publication completion | 2.460 | 2.447 |
| Total observed after proposal through in-worker publication | 11.792 | 11.038 |

The paid workers began at 12:55:40.142 and 12:56:10.654 UTC on 2026-11-24 and took 30.512 and 28.199 s through exit. Intermediate timestamps were retained as scoped durations. The existing confidence reads and scoring consumed 3.154 and 2.759 CPU s inside the proposals, already paid before this late audit. The full-20 proposal also used 0.926 CPU s to prepare and fit a repair that qualified. The hybrid used no such repair. Both accepted without a later repair or named fallback. [Solver timing scopes](blind_joint_route.py)

An independently qualified substitute installed before the signed step could replace at most 2.762 or 2.707 CPU s of that recorded signed step, minus its own cost. A diagnostic using the published curve book arrives after these fits. Nearly all other late work generates required grid and media evidence. Holding the decision longer or scoring an alternative family adds work to these measured single-pass successes. This audit therefore supplies neither a qualified runtime gate nor a claim that a full repeat can be eliminated.

A bounded later experiment would need actual competitor margins tagged to ordered curve IDs from a two-receiver-capable scorer, or frozen training predictions for a truly excluded RF group. Existing clocks set the budget for such a comparison. The cheaper proof here took 0.061 CPU s to verify the signed books and replay the stored cold criterion. It fitted no new model, calculated no orbit and read no waveform. Sixteen component and adjacent tests passed. The uncompressed audit SHA-256 is 42fee070bfc25dbcbbe0cf7f98ca2f4849b078c59b9fee311bc9b68c532ef88b.
