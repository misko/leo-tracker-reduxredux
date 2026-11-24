# DS30-0147 original-file fallback accounting

The verified installed run took 121.950 s and the successor took 127.697 s.
Both completed with both calibration arms, an evidence grid, and eight PNGs.
The successor attempted lean inference because the earlier-orbit census was
healthy. Its legal matched-support refit then failed the required curved
track agreement. The ordinary named solve and evidence took 59.334 s of the
79.192 s solver interval. A source-exact first-arm veto can avoid the second
refit. Both refits together consumed 0.529 s, the gross upper bound for
that change. Half-time needs 66.722 s of actual wall savings.

## Verified clocks

Receipt timings are wall seconds through raw-launcher exit and common
verification. Acquisition, decision, solve, and fallback are successor
only. Solve is inside decision and fallback is inside solve.

| Original-file pair | Installed | Successor | Acquisition | Decision and publication | Solve | Named fallback |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0147 | 121.950 | 127.697 | 42.963 | 82.858 | 79.192 | 59.334 |
| DS30-0220 | 117.961 | 56.418 | 40.379 | 13.976 | 10.521 | 0 |
| DS30-0019 | 107.018 | 71.490 | 53.194 | 16.543 | 12.729 | 0 |

On DS30-0147 the non-overlapping top-level wall and CPU scopes were as
follows. Other launcher work spans initialization and post-publication
receipt checks. The receiver-ready clock is cumulative and already
contained in that child clock.

| Raw successor stage | Wall | CPU |
| --- | ---: | ---: |
| Other launcher work | 0.734448 | 0.699255 |
| Authenticated acquisition | 42.963218 | 39.307847 |
| Held-anchor route selection | 0.594329 | 0.583901 |
| Decision and publication | 82.857671 | 81.481721 |
| Common verifier after child exit | 0.546967 | 0.546496 |
| Verified total | 127.696633 | 122.619220 |

The installed child took 121.399928 s wall and 108.738976 s CPU. Its common
verifier took 0.550198 s wall and 0.547394 s CPU. In the successor decision
interval, `analyze` took 81.183877 s including both solve and 1.589127 s of
rendering. Other work inside `analyze` took 0.402938 s and work outside
`analyze` took 1.673793 s. This avoids counting rendering twice.

| Nested solver scope | Wall | CPU |
| --- | ---: | ---: |
| Named prepare | 3.039614 | 2.948427 |
| Inference | 75.864815 | 75.358692 |
| Other solve work | 0.287384 | 0.152447 |
| Solve total | 79.191813 | 78.459566 |

| Ordered inference scope | Wall | CPU |
| --- | ---: | ---: |
| Lean cold proposal | 8.649938 | 8.400763 |
| Initial retained gate | 0.907504 | 0.899122 |
| Salvage | 4.084989 | 4.080747 |
| Provisional seed gates | 0.812309 | 0.810247 |
| Provisional isolation, zero fits | 0.005975 | 0.005973 |
| Predictive selection chronometer after reset | 0.332010 | 0.331811 |
| Original pair finish | 0.928598 | 0.928048 |
| Repair preparation | 0.220621 | 0.220513 |
| Both repaired arms | 0.528813 | 0.528449 |
| Unassigned within abandoned lean attempt | 0.001279 | 0.000817 |
| Original named fallback | 59.334098 | 59.093998 |
| Other inference work | 0.058681 | 0.058202 |

Cold rank (6-node output, 5.402804 s) and named rank (7-node output,
5.950299 s) are already inside their respective spans. The nomination
handoff records one speculative prefix set and rank excluded, followed by
one ordinary fallback. The trace supplies neither ordered-node identity
nor an input-equality witness that would authorize a full rank transfer.
Partial numerical reuse would require equality of projection inputs and
stable rank products. The sealed scalar counts do not establish that
equality. The case's acquisition is 10.231 s faster than the direct-success
control while the solver is 66.463 s slower.

## Gate decision

| Lean quality stage | c = 0 curved | Fitted c curved | Predictive, both arms |
| --- | ---: | ---: | ---: |
| Original joint finish | 2329 / 2329 | 2301 / 2329 | 776 / 776 |
| Repaired joint finish | 2210 / 2301 | 2210 / 2301 | 776 / 776 |

The first joint finish rejected one 28-observation curved track in the
fitted arm. Removing it used one of 107 tracks and preserved both radios,
24 curved families, every predictive observation, and 2018 residual degrees
of freedom. The fitted and fixed refits each rejected two new curved tracks
totaling 91 observations. Both refits retained all predictive support and
both finished inside the offer with small phase changes. The lean route
returned `repair_original_joint_pair_gate` before signed-history and
exterior qualification. The later named result also finished inside the
offer, so the boundary guard required no additional exterior solve.

The archived `history_policy.pair_passes` requires every curved track in
each arm to be compatible. The original `blind_joint_repair.repair_once`
finishes `c0` first, then fits `fitted_c`, then evaluates that conjunction.
`event_position` produces explicit Boolean curved gates. At the end of
the repaired `c0` fit the curve veto is already mandatory. The ordinary
named route is then called with the original `prepared` argument and
recreates its own `previous` and `genuine_previous` `ScanLikelihood`
objects. Its accepted inputs and publication ports do not consume the
discarded refit. The phase-width memo belongs to the discarded scan and
the local event-model cache belongs to its refit problem. No cheap earlier
predicate in the sealed route predicts the two new curved failures.
Earlier-orbit health applies equally to this case and successful lean
runs. Dispatching all such healthy inputs straight to the named path
would change the delivered science and timing on successful cases.

The default-off research prototype pins the historical repair and paired
policy sources. It returns the existing rejection and labels the actually
fitted and skipped arms when an ordinary curved track in repaired `c0`
already failed. Potentially qualifying pairs still execute both arms and
all original gates. The newer alternate conditional-repair path is outside
this pinned source, as it may consume the other arm. Local tests cover
original paired disposition, two-arm continuation, explicit skip evidence,
unrecognized gate values, and disabled or unpinned activation. No runtime
speed or byte parity is attributed to the prototype. The next needed
telemetry for this narrow change is one CPU and wall interval per repaired
arm. A potentially larger exact handoff would additionally need scoped
input hashes and timing from common preparation on both rank routes.

The observed named fallback used the successor's acquired packet. The
installed paired run used its own native detector and produced different
terminal endpoints. The observed named fallback's RF RMS was 151.323 /
151.148 Hz, fixed / fitted, compared with 124.477 / 124.524 Hz installed.
The initial lean RF RMS was 152.664 / 152.554 Hz and the rejected repair was
151.785 / 151.658 Hz. A lower RF RMS did not make the refit admissible.
No new geographic scoring was performed.

## Distinct controls and half-time

DS30-0220's verified original-file successor legally repaired and
accepted its pair in 0.237 s and never entered named fallback. The
authentic **separate full-detector saved** DS30-0220 control stopped at
`repair_rejection_cap` before refitting after 124 of 2445 curved
observations across three components were excluded. It retained all
predictive associations. Saved through-exit wall was 45.626 s with
33.204 s of named fallback. The separate one-refit over-cap challenge
then saw the repaired fixed arm fail while the fitted arm passed, followed
by 33.013 s of fallback and zero raw timing credit. DS30-0019 went directly
from lean fit through signed qualification and evidence without repair
or named fallback. There is no basis in these receipts to transfer the
full-detector route to the original-file domain.

DS30-0147's half-time was 60.975 s. Acquisition and the remaining measured
non-decision work leave 16.136 s for decision and publication, or 12.470 s
for solve with measured non-solver work held fixed. Removing the entire
observed fallback, including required work, would still leave 7.387 s of
excess. Removing all abandoned lean work with the named path retained
would leave 50.250 s of excess. Even free authenticated acquisition with
the observed solver intact would leave 23.758 s of excess. The only
source-demonstrable omission established here is one arm within the
0.529 s refit interval, versus an observed raw slowdown of 5.747 s.

Scope is a pinned main campaign export of 455 assignments / 910 arm rows.
It contains 22 observed pairs with matching verified original-file clocks.
DS30-0397's installed arm is a solver failure measured through exit
without a common publication verifier, so that case remains a disposition
outside these matched timing summaries. The table excludes pending and
detached work.

| Panel comparison | Pairs | Summed speedup | Paired median speedup | Excess over summed half-time |
| --- | ---: | ---: | ---: | ---: |
| Measured | 22 | 1.658× | 1.750× | 209.330 s |
| Omit DS30-0147 | 21 | 1.740× | 1.758× | 142.608 s |
| Hypothetical DS30-0147 exactly at half-time | 22 | 1.753× | 1.759× | 142.608 s |

The slowdown contributes 66.722 s, about 32% of net shortfall in this
snapshot. Even a full fix on this case leaves the same panel target gap on
the other cases. No new solver execution, lease, waveform, or orbital data
read took place in this audit.

The compact clock and gate receipt is `measurements/fallback-accounting-0147.json`
with SHA-256 `3df4617d85552ffe36b158f729c6d41f99ccb7d95f3de970b8f0b1570b966031`.
It binds all case receipts, the campaign export, the enrollment plan, and
the matched panel inputs. Historical source pins for the measured repair,
policy, route, and bootstrap are respectively `f89e80dd6560`,
`429c230cb014`, `f7a66aea7ed8`, and `217904f0268a`. The named core source
is `30e6f22ab4b4` and the event-position source is `3a8c9bde7ddd`.
