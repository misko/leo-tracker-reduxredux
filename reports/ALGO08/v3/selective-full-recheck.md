# Selective full-aperture recheck on two original first members

The candidate-only trigger selected **one of 110** original DS30-0163 lanes and recovered the exact installed 20 ms factor at visit **61**, receiver **0**, channel **6**. The unchanged chronological selector gave the stronger raw full alternative zero votes and the original rank-one alternative five. It retained **−49,126.353 Hz**, replacing the sparse selection **+68,872.210 Hz**. The separate DS30-0008 member triggered **zero of 128** lanes, kept all 70 measured factors and offers no test of recovery when the gate activates in a new recording. [Frozen decision](selective-full-recheck-protocol.md) · [Typed candidate results sealed before scoring](measurements/selective-full-recheck-receipt.json.gz)

## Original support and unchanged decision rules

The trigger sees the candidate’s actual original admitted chronology, including both radios and empty slots. It only considers a positive short lane with zero original chronological continuation votes and previously retained history for that receiver, edge, channel and actual RF. It uses the installed 12-opportunity and eight-second bounds. A second temporal pass sees the true installed two-scan full hypotheses on a flagged lane and the unchanged original candidate factors elsewhere. It can select any qualifying full hypothesis or emit empty. The initial trigger has no access to this pass’s replacements. Both detectors use the same signed window, hardware counter and acquisition clocks. The actual existing held-anchor EOF route then selects the modified prefix packet with a distinct research recipe. Neither named receiver answers nor archived owner IDs enter the worker or its policy. [Implementation](selective_full_recheck.py)

Earlier studies applied fixed-epoch CFO remeasurement to already continued lanes, tested exact preprocessing reuse when a full escalation was forced, or used short-verifier confidence to weight solver observations. The present recheck instead revisits an unsupported short atom in a stream with already accepted prior evidence. It permits different native epochs, alternative rank-one factors and an empty result under the same installed temporal rule. The 0163 visit 61 incident motivates the test, so its successful recovery is development evidence. The 0008 transfer was enrolled before opening any named lane answers for this experiment. It uses the existing genuine 20/8 generic packet under its original identity. The separate same-window sparse DSO check reproduced all 112 of that member’s short native factors byte for byte. [Earlier continued refinement](continued-cfo-live.md) · [Earlier forced overlap comparison](incremental-escalation.md) · [Independent sparse DSO parity](short-rank.md)

The original 0163 member completed 64 issued visits, 55 admitted and nine exclusions. The dense 0008 member had 64 issued and admitted visits. Both new selected packets preserve the real original clock bracket, delivery clocks, last counter, signed member authority and lane opportunities. Nothing outside either exact first member was read. The 0163 output’s held EOF selector stayed unfiltered with log history gains **−2.25479 / +0.28620**. The unchanged 0008 packet also stayed unfiltered, with **−7.84031 / −3.23662**. [Existing complete 0163 member](first-member-0163-resume.md) · [Existing complete dense member](original-dense-intake.md)

## Actual work and limits

| Incremental scope | DS30-0163 | DS30-0008 |
|---|---:|---:|
| Candidate-only shortlist CPU | 0.404 ms | 0.481 ms |
| Actual 20 ms native rechecks / CPU | 1 / 5.944 ms | 0 / 0 ms |
| Released original-member read/decode/verification CPU | 207.884 ms | 0 ms |
| Full native context initialization CPU | 2.081 ms | 0 ms |
| Replacement chronology CPU | 0.155 ms | 0.196 ms |
| Existing held EOF CPU | 6.268 ms | 6.606 ms |
| Immutable detector write CPU | 0.308 ms | 0.376 ms |
| Fresh incremental child through exit, wall / CPU | 1.296 / 1.112 s | 0.940 / 0.811 s |

The replay begins with already acquired signed detections. DS30-0163 reread its full existing local compressed member through the installed decoder before producing a new detector packet. The exact decoder timer and full callback account for only part of the process. The detached harness also paid first-use imports and local checks. On 0008 the as-run `full_lookup` initializes its Python dependencies before checking the empty schedule, charging **539.043 ms CPU** even though it opens no waveform and runs no full native call. These process-level costs apply to the measured detached wrapper. The native and chronology clocks isolate work relevant to a future inline implementation. No inline or acquisition-through-position clock was measured. An initial 0163 wrapper stopped at the first resident window before any full callback at **1.297 s wall / 0.980 s CPU** because its receiver-order field belongs to the signed segment. That scope is separately sealed. Corrected runs used the original scan’s segment port and unchanged trigger, one shared low-priority lease per case. [Native, reader and failure clocks](measurements/selective-full-recheck-receipt.json.gz)

## Post-seal comparison with named policy

| Named agreement | DS30-0163 before → after | DS30-0008 before → after |
|---|---:|---:|
| Positive lane precision | 8/36 → 8/36 | 17/70 → 17/70 |
| Positive lane recall | 8/8 → 8/8 | 17/19 → 17/19 |
| Exact typed factor precision | 0/36 → 1/36 | 0/70 → 0/70 |
| Exact typed factor recall | 0/8 → 1/8 | 0/19 → 0/19 |

The corrected 0163 lane is the only changed packet row and no prior positive or identical factor was lost on either member. The dense candidate’s two missed named lanes and 53 candidate-only positives are unchanged. The sparse policy emitted a positive where the named policy did not at 28 0163 lanes, also unchanged. These disagreements describe the named temporal policies on these prefixes and do not establish radio false-positive rates. The exact factor comparison includes the native rank, epoch, CFO, recorded scores and other typed fields. The 0163 full candidates were **−112,782.582 Hz, rank 0** and **−49,126.353 Hz, rank 1**. The second was selected from the actual two-scan return by the unmodified temporal rule. There was no matching against the named answer until the pair was sealed. [Exact comparison and counts](measurements/selective-full-recheck-score.json)

Three component tests passed. The as-run worker is `a31613fc6`. The two candidate outputs were sealed at `f690d58f5` before named-policy scoring. The test did not read original backing media, perform RF collection or run any position solver.
