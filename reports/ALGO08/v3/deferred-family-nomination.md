# Deferred nomination after singleton family closure

The DS30-0220 second-screen tape yields one unique same-family peer
pair, but **zero new hypotheses**. Ordinary salvage had already selected
both exact intervals and the isolated salvage procedure had already
considered the failed peer. Both curves are on the same receiver. The
frozen nomination therefore stops before an independent fit. No gates
or published owners change. DS30-0086 has no singleton closure and
produces no nomination.

| DS30-0220 active component | Lane | Points | Original second-screen evidence |
| --- | --- | ---: | --- |
| T005, 11,440.3125 MHz | RX1 / CH3 | 17 | Passes every individual test, then fails singleton family closure |
| T006, 10,940.3125 MHz | RX1 / CH1 | 21 | Conditional slope and separate profile noise fail |

Both rows belong to the selected NORAD 57791 family. There is exactly
one eligible different-lane peer and zero different-radio peers in the
second tape. The 17-point interval is entirely within the 21-point
peer's 28.375 s span. The direct survivor had conditional slope z
2.228. The peer had z 3.005866 against the released limit of 3.0, with
the other recorded conditional tests passing. The original profile
noise Boolean also failed. The tape alone does not attribute that
profile failure to slope and returns `unknown_profile_failure`.

The frozen full charted receipt already records T006 in the isolation
`eligible` set. The pinned source evaluates `sole_failure(slope_z)` for
both conditional and profiled noise on the same post-salvage problem,
coordinates and active interval as the second screen. The stage's
actual input and output ownership hashes reproduce the earlier charted
support masks. The full charted receipt's selected alias is zero at
both intervals. These source and receipt bindings prove the profile
classification without inferring its z value or loosening the gate.

Ordinary salvage selected T006 `[0, 21)` and T005 `[0, 17)` and had
already considered four shorter T006 and three shorter T005 intervals
of the same family. The matching full intervals both entered the
original second-screen problem, where they were rejected. The original
isolated candidate set contained T006 and two other qualifying curves
on different families. Its uniqueness check ran zero isolated fits.
Singleton closure thus contributes a different reason for prioritizing
one of three existing options. It contributes no new discrete interval
or family assignment and no independent radio. The original predictive
list contained no 57791 candidate, and signed history did not qualify.
A later test would need a newly justified hypothesis and an independently
reserved radio or time block under the existing alias and noise gates.
Nothing in these tapes supplies that independent evidence.

## Coverage after the nomination seal

The same mixed-packet installed and charted terminal owner maps were
rebound to their recorded digests after the nomination was committed.
The counts below apply separately and identically to fixed and fitted
calibration. The owner join compares the observation, satellite and role.

| Case and counterfactual scope | Installed-only owners matched | Wrong satellite or role | Extra relative to installed | All installed-only owners |
| --- | ---: | ---: | ---: | ---: |
| DS30-0220 closed curve alone | 17 | 0 | 0 | 187 |
| DS30-0220 failed peer alone | 21 | 0 | 0 | 187 |
| DS30-0220 both intervals | 38 | 0 | 0 | 187 |
| DS30-0086 inactive control | 0 | 0 | 0 | 75 |

Closing this one gap could recover at most **9.1%** of all 0220
installed-only owners directly, or **20.3%** if future evidence admitted
both intervals. The latter is **21.2%** of the 179 missing conditional
owners and leaves 149 of all missing installed owners outside the
proposal. The diagnostic adopts zero assignments. These owner counts
provide no position or refit-time estimate.

The observed tapes and source were checked against custodian commit
`8fa3872d7db96babacad8a5f2d12dfa449caa136` and gzip SHA-256
`6eb9e46220096e695eaddfb5b4b0a673d8a28d13035e7caf8a26b9fc5f7df995`.
The raw 0220 and 0086 after-salvage tape digests begin `6e2d1e2a663d`
and `80cf9bdba526`. Eight component tests passed. The metadata replay
started no solver, instrumentation, waveform, or orbit reads.

[Frozen protocol](deferred-family-nomination-protocol.md) ·
[Owner-blind prediction](measurements/deferred-family-nomination-prediction.json) ·
[Post-freeze comparison](measurements/deferred-family-nomination-scored.json)
