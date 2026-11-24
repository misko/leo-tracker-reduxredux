# DS30-0073 transfer of the frozen first-arm repair veto

The unchanged DS30-0147 veto fires on DS30-0073. The **completed repaired
`c = 0` fit** marked `SCAN-RX1-CH8-T002-RF12459687500.000000`
incompatible across its 86 retained observations. The fitted arm also
failed that component. The frozen predicate can therefore omit one
fitted-arm repair fit and return the original named-fallback reason.
Both refits together took **0.646 s wall / 0.645 s CPU**, the gross
upper bound. The saved trace times the refit loop as a whole, so the
individual fitted-arm saving is unmeasured.

| Joint finish | `c = 0` curved compatible | Fitted `c` curved compatible | Predictive compatible, each arm |
| --- | ---: | ---: | ---: |
| Original | 3076 / 3133 | 3039 / 3133 | 490 / 490 |
| Repaired | 2953 / 3039 | 2953 / 3039 | 480 / 480 |

The original `c = 0` fit failed RX1 CH6 T003 (57 points, selected salvage
NORAD 64214, alias 1). The fitted arm failed that track and RX1 CH8 T006
(37 more points, NORAD 53171 and alias 1 in the sealed cold signatures).
The support repair removed both curved tracks and RX1 CH6 T014 predictive
(10 observations, selected NORAD 53171, alias 0). Neither original
predictive gate failed. RX1 still had active upper-band support after
repair, as shown by the 86-point CH8 T002. Under the pinned
`retained_entries` rule this identifies loss of the predictive entry's
retained curved family as the support veto. The repair was eligible with
three of 102 tracks removed, two radios, 21 curved families and 2827
residual degrees of freedom.

The newly incompatible T002 retained the salvaged NORAD 64214 assignment
at alias 1. The repaired endpoints were inside the 25 km offer and the
phase changes were 0.000522 s / 0.000406 s, below the existing 0.01 s
limit. The pinned `retained_metrics` emits a Python Boolean and the
pinned `readout` emits exactly the failed curved components. Feeding
that sealed failure projection to the unchanged `completed_curved_veto`
returns true. The receipt does not break down the residual, noise,
alias, elevation and orbital-owner clauses of that track's composite
gate. The separate reverted provisional salvage does contain detailed
diagnostics for its own target, which is a different component.

| Verified original result | Wall | CPU |
| --- | ---: | ---: |
| Installed, including verifier | 125.541 s | 108.863 s |
| Successor, including verifier | 100.148 s | 94.595 s |
| Successor solve | 50.351 s | 50.123 s |
| Abandoned lean attempt, inside solve | 9.875 s | 9.751 s |
| Named fallback, inside solve | 37.911 s | 37.867 s |
| Repair preparation, inside abandoned lean | 0.251 s | 0.250 s |
| Both refits, inside abandoned lean | 0.646 s | 0.645 s |

The original named fallback rebuilds science from the successor's
complete acquired packet. Each published arm has the same 3433 ordered
owners, with 2953 conditional observations and 480 predictive. The
counts agree with repaired compatibility totals. The discarded repair
readouts omit the per-observation owner lists and cannot establish that
those rows or assignments are identical. Both raw results are verified
complete with 179 grid sites and eight PNGs. The paired installed worker
used its own detector packet. The prototype leaves the named fallback
and all its required science work intact. At the unattainable ceiling
of removing the entire refit loop, the verified wall would still be
36.732 s above half-time.

DS30-0147 remains the original control. It emitted two incompatible
curved components in repaired `c = 0`, and its two-refit ceiling was
0.529 s wall. DS30-0073 is a second observed trigger on the original
route, with a different support-removal pattern and same mandatory
Boolean. This is a receipt-backed transfer of the unchanged predicate,
with no timed solver, waveform or orbit access. The original prototype
and control files are unchanged.

The evidence is in `measurements/repair-veto-transfer-0073.json`,
SHA-256 `4b3efdaf6970e8107260b12e9a6f6abe06fd0179ed96bf96942029699c41a2d3`.
The receipt binds the next-three export, both original raw results, the
charted sources and the frozen prototype on commit `10497fa98`.
