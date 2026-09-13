# Radio .20: bounded ARM frequency revisit plans

The ARM controller now accepts two to four upper-edge frequency visits,
including a return to an earlier frequency. All **250 focused tests pass**
and the Cortex-A9/NEON build succeeds. A subsequent physical 30-MS/s run now
verifies CH3 → CH4 → CH3 under one ARM parent: 21.0666876 seconds of RF,
zero active source drops and passing independent reviews. There is no
acquisition handoff, so sustained tracking and clean-loss continuation remain
unqualified. The four-visit and 60-MS/s extensions still need physical checks.

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
settings and TX disabled, then removes its temporary files. The last verified
state is now 30 MS/s at **CH3 upper**, serial
`1040005e0b100007100010000bf33a5d4d`. The staged binary is removed after the
bounded test; this is not a persistent tracking service.

The [physical evidence manifest](figures/2026_09_13_radio20_arm_frequency_revisits/physical30-evidence.json)
retains the operator and passing child/sequence reviews, with source hashes.
SHA-256: `33fe5816be6eec1632f659d9b798b647d3cafe5b3c1d0d0845c848579d1f9ba3`.
Operator/reviewer sources, admission tests and transition mutation results
are retained beside it. Review change `ead0397c7` is a local firmware-worktree
commit. Sustained tracking, physical clean-loss continuation, adaptive
revisits and precision refinement remain incomplete.
