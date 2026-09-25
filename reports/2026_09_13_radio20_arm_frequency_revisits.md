# Radio .20: bounded ARM frequency revisit plans

The ARM controller now accepts two to four upper-edge frequency visits,
including a return to an earlier frequency. All **250 focused tests pass**
and the Cortex-A9/NEON build succeeds. A subsequent physical 30-MS/s run now
verifies CH3 → CH4 → CH3 under one ARM parent: 21.0666876 seconds of RF,
zero active source drops and passing independent reviews. There is no
acquisition handoff, so sustained tracking and clean-loss continuation remain
unqualified. The same three-visit plan now also passes physical and independent
checks at 60 MS/s (21.0077364 seconds of RF). After the shared lease becomes
available, a four-channel 60-MS/s sweep also passes physical and independent
checks (28.3947288 seconds of RF), with no handoff.

The previous composition accepted only two distinct centers. The new plan
can express CH1 → CH2 → CH3 → CH4 or CH3 → CH4 → CH3. It validates every
center and rejects adjacent duplicates before creating evidence or calling
radio ports. Each transition still requires retained idle/fixed-RF evidence,
advancing source coordinates, completed child cleanup and a valid global
deadline. The old two-visit entry point and wire output remain compatible.

| Component / limit | Two visits | Three or four visits |
| --- | --- | --- |
| FPGA/native source rate | 30 or 60 MS/s | 30 or 60 MS/s |
| ARM IQ rate | 2.5 MS/s | 2.5 MS/s |
| Per-visit capture limit | 1,536 blocks; 10.0663296 s | Same |
| Per-visit acquisition attempts | 6 | 6 |
| Shared parent deadline | 60 s | 60 s, including revisits |
| IQ retention | Full returned stream | Selected scan/worker/observer windows |
| Maximum total RF | 20.1326592 s | 30.1989888 or 40.2653184 s |

Four full raw streams alone would occupy 384 MiB, exceeding the existing
352-MiB temporary evidence filesystem before worker and native evidence.
The longer plans therefore use a finite `1536-selected` profile, reusing the
existing selected-window recorder with a 12-second worker budget and a
25-second child alarm. Complete source counters and native/observer journals
remain retained. This reduces storage but removes complete-stream IQ evidence;
source association must be checked through retained views and overlapping
windows. Hardware resource qualification remains required.

Clean native loss in visit mode returns to the parent after cleanup. It does
not initiate a same-frequency REBASE inside the child. Ordinary capture,
retention, cancellation and cleanup failures still stop the plan. Frequency
order is prescribed by the plan; this is not adaptive frequency ranking.

Tests cover both rates, three-visit return and four-visit sweep ordering,
nonadjacent repeats, rejection of invalid later entries before I/O, failures
in the third visit, clean-loss ownership in the selected profile, and actual
four-child fork/wait with separate evidence files. These use simulated radio
ports and do not prove physical tracking or hardware retune behavior.

Firmware commit: `3db06b7adf5e366b653485d642942585708127df` (local firmware
worktree, not pushed by this report publication).
ARM binary SHA-256:
`2dfe31cc68d8f9fd5dd63fe0ae284aa7fe95de721a8f716dc279681a0c2ea0b2`.
The [component patch](figures/2026_09_13_radio20_arm_frequency_revisits/component.patch)
and [250-test result](figures/2026_09_13_radio20_arm_frequency_revisits/tests.xml)
are retained for review.

## Physical three-visit result

The operator and independent source/arithmetic/transition reviewers now
support the selected-IQ multi-visit plan. Ten no-radio admission tests verify
valid plans and lease refusal at both rates, and reject invalid plans before
identity access or evidence creation. Six focused clean-loss/profile tests
also pass; these overlap the preceding component suite. The clean-loss
reviewer now accepts the selected retention mode while preserving its native
horizon, drain/clear and observer-join requirements.

`frequency-revisits30-v1` staged the hash-pinned ARM binary on `.20` under
the normal global and serial leases. The frozen 30-MS/s FPGA image and boot
identity remained unchanged. No host command selected a frequency between
visits; the radio-local parent owned all three transitions.

| Visit | Actual LO | Epoch | Exported RF duration | Attempts / handoffs | Active CDC/pacer drops | Maximum refill gap |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| CH3 upper | 1,690,312,498 Hz | 5 | 6.9480060 s | 6 / 0 | 0 / 0 | 6.933948 ms |
| CH4 upper | 1,940,312,500 Hz | 6 | 6.9610048 s | 6 / 0 | 0 / 0 | 6.970374 ms |
| Return to CH3 upper | 1,690,312,498 Hz | 7 | 7.1576768 s | 6 / 0 | 0 / 0 | 6.726306 ms |

The returned block counts are 1,060, 1,062 and 1,092. All 18 acquisition
attempts reject their past measurements; no native descriptor or observer
episode starts. Independent checks verify 659,934 integer acquisition-grid
values, 144 moment/dense fits, retained-IQ overlap consistency, source counters
and all nine parent transition records. Eight deliberately corrupted fields
in the third visit's final record are rejected, including false clean loss,
wrong LO/epoch/counter/rate, visit number and idle/fixed-RF flags.

Retained artifacts total 8,739,256 bytes. This includes selected scan/worker IQ
and journals, not the complete returned stream. Source association therefore
uses retained views, counter continuity and overlapping cuts; it cannot offer
the full-stream cross-check available in the earlier two-visit tests.

The operator verifies unchanged serial/firmware/boot identity, fixed receive
settings and TX disabled, then removes its temporary files. At the end of this
30-MS/s run the radio is at **CH3 upper**, serial
`1040005e0b100007100010000bf33a5d4d`. The staged binary is removed after the
bounded test; this is not a persistent tracking service.

The [physical evidence manifest](figures/2026_09_13_radio20_arm_frequency_revisits/physical30-evidence.json)
retains the operator and passing child/sequence reviews, with source hashes.
SHA-256: `33fe5816be6eec1632f659d9b798b647d3cafe5b3c1d0d0845c848579d1f9ba3`.
Operator/reviewer sources, admission tests and transition mutation results
are retained beside it. Review change `ead0397c7` is a local firmware-worktree
commit. Sustained tracking, physical clean-loss continuation, adaptive
revisits and precision refinement remain incomplete.

## Verified 60-MS/s revisit

The frozen 30-to-60-MS/s image transition completes successfully, including
source identity/idle checks, staged-image hashing, updater completion, MTD3
FIT verification, reboot/return attestation and TX-safe verification. The
deployment receipt is `0afb2dfe-42c4-43f7-84eb-0d5d29dfd6cb`; returned image
`glrt-iq-tracking-r60000000-v1` has FIT SHA-256
`19c1504e8cbf442f4fd2ee995a0ceaf3780a9a4559026a653f8fdaae53932f1b`.
The returned boot is `ba41bda7-09ad-40e3-973d-4a8f070b35be`.

`frequency-revisits60-v1` then runs the same ARM binary and CH3 → CH4 → CH3
plan. Native sampling is 60 MS/s and ARM IQ remains 2.5 MS/s.

| Visit | Actual LO | Epoch | Exported RF duration | Attempts / handoffs | Active CDC/pacer drops | Maximum refill gap |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| CH3 upper | 1,690,312,498 Hz | 1 | 7.0068464 s | 6 / 0 | 0 / 0 | 6.701136 ms |
| CH4 upper | 1,940,312,500 Hz | 2 | 7.0529468 s | 6 / 0 | 0 / 0 | 6.705678 ms |
| Return to CH3 upper | 1,690,312,498 Hz | 3 | 6.9479432 s | 6 / 0 | 0 / 0 | 6.851460 ms |

The total is 21.0077364 seconds of RF. All eighteen acquisition attempts
reject their past measurements; no handoff, native measurement or observer
episode occurs. Independent selected-IQ/source/arithmetic reviews and all
nine retained parent transitions pass. The initial epoch-zero counters are
also zero. Artifacts total 8,730,593 bytes; the same selected-IQ evidence
limits apply as in the 30-MS/s test.

The operator verifies unchanged image/boot identity across capture, fixed
receive settings and TX disabled, and removes its temporary files. At the end
of this three-visit run the radio is **60 MS/s at CH3 upper**, serial
`1040005e0b100007100010000bf33a5d4d`. This is a bounded ARM-controlled revisit
at both rates, not a persistent service or a supported tracking episode.

A subsequent CH1 → CH2 → CH3 → CH4 sweep attempt is refused before radio
contact because the shared acquisition lease is busy. The owning acquisition
process, PID 671581, was verified live; the lease was not bypassed. That
attempt collected zero RF samples and is retained as `frequency-sweep60-v1`.

The [60-MS/s evidence manifest](figures/2026_09_13_radio20_arm_frequency_revisits/physical60-evidence.json)
includes the successful deployment result, completed capture/reviews and the
refused four-visit attempt. SHA-256:
`ec9ce738675b1bf59f60602dc8185758896558453d76120d6d9741afd2113f4d`.
Sustained tracking, physical clean-loss continuation, adaptive revisits and
precision refinement remain incomplete.

## Verified four-channel 60-MS/s sweep

The shared-lease owner PID 671581 was rechecked and remained live, then its
process handle disappeared. A fresh attempt, `frequency-sweep60-v2`, acquired
the normal leases and executed CH1 → CH2 → CH3 → CH4. The original refused
attempt remains preserved; no lock was bypassed and no firmware changed.

| Visit | Actual LO | Epoch | Exported RF duration | Attempts / handoffs | Active CDC/pacer drops | Maximum refill gap |
| --- | ---: | ---: | ---: | --- | --- | ---: |
| CH1 upper | 1,190,312,500 Hz | 4 | 6.9806984 s | 6 / 0 | 0 / 0 | 7.496844 ms |
| CH2 upper | 1,440,312,500 Hz | 5 | 6.9741244 s | 6 / 0 | 0 / 0 | 6.767904 ms |
| CH3 upper | 1,690,312,498 Hz | 6 | 7.1052560 s | 6 / 0 | 0 / 0 | 7.818144 ms |
| CH4 upper | 1,940,312,500 Hz | 7 | 7.3346500 s | 6 / 0 | 0 / 0 | 7.329942 ms |

The run exports 28.3947288 seconds of RF within its 40.2653184-second cap.
All 24 attempts reject their past measurements; no native descriptor or
observer episode starts. Independent review passes all four visits, including
879,912 integer acquisition-grid values, 192 moment/dense fits, retained-IQ
overlap checks, source counters and all twelve parent transition records.

Selected-IQ artifacts total 11,682,210 bytes. This verifies execution of the
longer plan with the selected recorder, not complete-stream IQ retention.
The operator verifies unchanged image/boot identity, fixed receive settings
and TX disabled, then removes its temporary files. The last verified radio
state is now **60 MS/s at CH4 upper**, serial
`1040005e0b100007100010000bf33a5d4d`, on boot
`ba41bda7-09ad-40e3-973d-4a8f070b35be`.

The [four-channel evidence](figures/2026_09_13_radio20_arm_frequency_revisits/sweep60-evidence.json)
retains the operator, four child reviews, sequence review and prior refusal.
SHA-256: `ecadfb4b7d7a1633d6977fa31866483b8598294c536a553ebbb78ae294db9c5e`.
Bounded three-visit operation is physically verified at both rates, and a
four-channel sweep is physically verified at 60 MS/s. These results do not
establish sustained tracking, physical clean-loss continuation, adaptive
frequency selection or precision refinement.
