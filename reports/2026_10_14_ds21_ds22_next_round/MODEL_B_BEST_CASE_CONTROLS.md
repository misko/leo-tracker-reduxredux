# Model B: best-case controls do not support curvature as the error explanation

The same frozen-source, training-only tangent diagnostic was run on the best
two cases from the original five-case B comparison: 005 and 003. Both completed
with zero optimizer calls, no held preparation, and no reference lookup. These
controls change the interpretation of the earlier worst-case result: timing and
calibration confounding is substantial, but its local magnitude does not rank
the observed position errors.

| Original B case | Historical CH1–8 error km | Fixed nuisance curvature | Timing free | Timing and calibration free |
|---|---:|---:|---:|---:|
| 005, best | 1.271893 | 4911.2734 | 13.2907 | 1.7848 |
| 003, second best | 2.346276 | 6477.6397 | 15.1342 | 8.2317 |
| 023, second worst | 5.599817 | 7688.2710 | 27.7761 | 7.4329 |
| 039, worst | 8.599847 | 5377.0242 | 26.1359 | 13.6114 |

All curvatures are the weakest horizontal eigenvalue of the linearized
observed-mixture objective, including the original priors, in NLL/km². They
include assignment uncertainty. These are not calibrated confidence intervals
or the full orbit Hessian. Historical errors come from the unchanged original
shared-six comparison; no new positions or reference errors were computed here.

Case 005 loses about 2752× in weakest curvature when both nuisance families are
profiled, versus 395× for 039. Yet 005 has much lower historical position error.
Its joint all-band curvature (1.7848) is also below its low-only (6.7417) and
high-only (2.6498) curvatures, even though its original combined position is
better than both halves. The half results still share discovery and proposals;
this does not establish an independent end-to-end band-only comparison.

This is a counterexample to using stronger local curvature, or a smaller timing
confounding ratio, as a proxy for better localization. It does not disprove a
timing-model error: timing can still absorb bias. However, it rejects that
local ambiguity alone is a sufficient explanation of the observed failure
ranking. The preceding full-objective directional checks on 039/023 support
the local calculation without finding a nearby downhill correction.

The next B intervention therefore needs a discriminating check of model bias,
satellite-association consistency or competing geographic modes. Blanket
timing-prior tightening remains unsupported by these results. Any new selector
must use training evidence and be frozen before reference evaluation; no
per-recording choice by known position error is permitted.

The 005 and 003 diagnostics took 14.068 and 16.377 seconds respectively,
including 10.980 and 13.983 seconds of preparation. Each used three objective,
three orbit-derivative and three standalone likelihood-oracle evaluations,
under the existing 180/195/200-second bounds. All original model, candidate,
partition, source and input guards passed. Each experiment remained fitted-c
only. Local receipts are in `local/model-b-best-control-005` and
`local/model-b-best-control-003`; their pre-preparation authority is
`local/model-b-best-controls-freeze/protocol.json`, SHA-256
`7843d618286ad7ecec15ee1e5a2ac97cbd958e07f68f38207d8438334ee475f1`.
