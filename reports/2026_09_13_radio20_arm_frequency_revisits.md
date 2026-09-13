# Radio .20: bounded ARM frequency revisit plans

The ARM controller now accepts two to four upper-edge frequency visits,
including a return to an earlier frequency. All **250 focused tests pass**
and the Cortex-A9/NEON build succeeds. This extension is not yet deployed or
physically qualified; no new RF was collected.

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

The next required work is adapting the hardware operator and independent
source/arithmetic/transition reviewer to the selected-IQ multi-visit plan,
then a bounded physical run. The last physical state remains
[30 MS/s at CH4 upper, TX disabled](2026_09_13_radio20_clean_loss_visits.md)
on serial `1040005e0b100007100010000bf33a5d4d`. Sustained tracking, physical
clean-loss continuation, adaptive revisits and precision refinement remain
incomplete.
