# Radio .20: bounded ARM-local frequency visits

The ARM can now run two bounded upper-edge visits and change the receive LO
between them without a host command for each visit. The corrected physical
60-MS/s run now passes exact parent snapshot/transition association and both
child source/IQ/arithmetic reviews. **This bounded two-visit path is verified at
60 MS/s; sustained tracking and physical 30-MS/s visit qualification remain
incomplete.** The initial snapshot-recording defect and intervening lease
refusal are retained separately below.

The firmware-worktree implementation starts at `c2a6d5f9f`; the corrected
version is `fd72f856e2de4c370c3e930f800c7b1c2950a285`. It extends the
[live observer composition](2026_09_13_radio20_live_passive_observer.md) toward
radio-local scanning across frequencies. These firmware commits are local;
publishing this report does not imply the firmware branch was pushed.

## Behavior and boundaries

The ARM parent accepts exactly two distinct nominal upper-edge IF centers from
channels 1–4. It retains the plan, verifies the fixed native image and receive
settings, and permits LO changes only with capture disabled and the tracking
engine drained and cleared. It changes no clock, bandwidth, gain or TX setting.
Lower-edge frequencies are rejected because this image uses the upper-edge
reference bank.

Each forked child runs the existing acquisition/native-feedback probe with
1,536 blocks, six acquisition attempts and 10.0663296 seconds of coarse IQ.
The parent reaps the child, checks and retains its terminal idle state and
source epoch/counter advance, and then permits the second tune. Every visit
has its own exclusive directory and native/observer evidence files. A child
failure stops the loop even if cleanup succeeds; it is not treated as a clean
tracking loss merely to continue scanning.

The two visits allow at most 20.1326592 seconds of RF. The supervisor uses a
60-second deadline, with a two-second termination grace for an unresponsive
child. Its child-process test covers both ordinary failure and forced
termination/reaping. The host operator holds the shared acquisition and
serial-specific leases for the complete sequence, verifies image/reference
identity, configures and calibrates RX once, and retrieves evidence afterward.

| Function | Location | Input sample rate |
| --- | --- | --- |
| Visit ordering, idle checks and LO changes | ARM parent | No IQ processing; verifies 30 or 60 MS/s native state |
| Continuous receive/decimation | FPGA | 30 or 60 MS/s → 2.5 MS/s |
| Acquisition and coarse observer | Child's ARM threads | 2.5 MS/s |
| Scheduled native measurements | FPGA, controlled by child ARM worker | 30 or 60 MS/s |

The initial plan visits CH3 upper, then CH4 upper: nominal IF centers
1,690,312,500 and 1,940,312,500 Hz. These coordinates follow the repository's
[channel tuning table](../docs/concepts/starlink-transmissions.md), not a new
frequency calibration or evidence of an active transmitter.

## Tests and physical captures

The initial integration run passes **140 tests**: 50 visit-controller cases,
four actual fork/evidence/lifetime cases, and 86 existing live-probe cases.
The controller cases cover both native rates, invalid/lower-edge plans, busy
or malformed source states, RF changes, counter/epoch regressions, deadlines,
cancellation and retention errors. After the snapshot fix, the 54 focused
visit and child-lifetime tests pass again. Both ARM builds use Cortex-A9/NEON
optimization with warnings treated as errors.

The first executable runs on `192.168.1.20`, serial
`1040005e0b100007100010000bf33a5d4d`, with the 60-MS/s image:

| Visit | Actual LO | New epoch | Captured coarse samples | Attempts | Accepted startup/native results |
| --- | ---: | ---: | ---: | ---: | ---: |
| CH3 upper | 1,690,312,498 Hz | 4 | 25,165,824 | 6 | 0 / 0 |
| CH4 upper | 1,940,312,500 Hz | 5 | 25,165,824 | 6 | 0 / 0 |

Each capture lasts 10.0663296 seconds and reports zero CDC/pacer drops. Maximum
refill intervals are 7.408632 and 7.229256 ms. Independent child review checks
all 3,072 returned-buffer source snapshots, both complete IQ files, 439,956
coarse-grid values and 96 startup moment/dense-fit records. Retained analysis
windows match the corresponding original IQ exactly. Both children finish
with cleared, drained tracking state. No handoff or observer episode occurs.

The operator verifies unchanged image/boot identity, disabled TX, the expected
final LO and unchanged remaining RF settings, then removes its own temporary
files. The radio remains on the 60-MS/s image at the CH4-upper LO after this run.

## Snapshot defect and corrected retry

The initial parent inspected one native snapshot, then read a second snapshot
for its journal. The free-running native counter advanced between those reads,
so the visit-state counter did not match the persisted snapshot. The independent
sequence reviewer rejects that exact association. The two child captures have
their own valid counter evidence, but they cannot repair the missing parent
association.

The corrected parent parses, validates and retains one exact snapshot. Its
binary SHA-256 is
`14f1a00362dabae444d4ecb6f234feda9b30eec00e897cf43fb762f76fea4b14`.
The first binary is preserved with SHA-256
`2c18f434b24b7835d81a6187a3953f9316fb4ade0f0af593f9fe21d6ef5ddf78`.

The corrected retry is recorded as `admission_refused`, with zero RF samples:
an acquisition process for radio `003a` held the shared global lease. That
process was not interrupted and its lease was not bypassed. After that process
exited, a fresh bounded run executed the corrected binary.

## Corrected physical result

The corrected run completed CH3-upper and CH4-upper visits at 60 MS/s, each
lasting 10.0663296 seconds. Its actual LOs were again 1,690,312,498 and
1,940,312,500 Hz. The first child advanced epoch 5 to 6; the second advanced
epoch 6 to 7. All six before-tune, tuned and after-run transition records now
match their exact retained native snapshots. Snapshot generations and native
counters advance monotonically, and the children bind to the expected epochs.
Six deliberate mutations of LO, rate, epoch, counter and idle/fixed flags are
rejected by independent sequence review.

Both child captures again pass full-IQ, grid, resolver, startup moment/fit and
source-counter checks. Each completes six rejected acquisition attempts,
25,165,824 coarse samples, zero CDC/pacer drops and no native handoff. Maximum
refill intervals are 7.254840 and 6.712590 ms. The operator confirms unchanged
image/boot identity, disabled TX and expected final RF settings, then removes
its temporary files. The final image remains 60 MS/s at CH4 upper.

The initial and corrected physical runs collected **40.2653184 seconds of RF
in total**; the refused attempt collected none. This result proves the fixed
two-frequency scan transitions in this run. It does not prove support-bearing
tracking, an adaptive revisit policy, continuation after native loss or
physical operation of this visit composition at 30 MS/s.

The [evidence manifest](figures/2026_09_13_radio20_arm_frequency_visits/evidence.json)
retains both binary hashes, test receipts, the physical child reviews, the
rejected parent association and the retry refusal. The separate
[corrected evidence](figures/2026_09_13_radio20_arm_frequency_visits/evidence-corrected.json)
contains the successful sequence review, both child reviews and mutation
checks, preserving the original failure evidence unchanged. Adaptive revisits,
continuation after qualified native loss, sustained tracking at both rates and
precision refinement remain unqualified.
