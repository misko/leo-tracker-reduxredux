# Radio .20: verified 30-MS/s frequency visits and admission correction

Radio `192.168.1.20`, serial `1040005e0b100007100010000bf33a5d4d`, is now running
the verified `glrt-iq-tracking-r30000000-v1` image. The first two-frequency test
stopped before capture because its preflight incorrectly applied acquisition
drop requirements to epoch-zero boot/calibration counters. The correction
passes 182 tests and builds for ARM. After one retry was refused by the shared
acquisition lease, the corrected physical run completed both visits and passed
independent review. **Bounded frequency visits now pass at 30 and 60 MS/s;
sustained tracking remains unqualified.**

This follows the [verified 60-MS/s visit path](2026_09_13_radio20_arm_frequency_visits.md).
The completed plan visits CH1 and CH2 upper edges, extending coverage beyond the
recent CH3/CH4 tests without changing the upper-edge reference or acceptance
gates. Nominal IF centers are 1,190,312,500 and 1,440,312,500 Hz. The same ARM
parent and finite child composition limits the pair to 20.1326592 seconds of
2.5-MS/s RF capture, with native measurements configured for 30 MS/s.

## Deployment evidence

The frozen 60-to-30-MS/s transition passes local image/extraction/rollback
verification, source identity and idle attestation, staged-image hash checking,
updater completion, MTD3 FIT verification, reboot and return attestation.
The returned serial and firmware match, TX remains disabled, and the SSH host
key is rotated only after the attested return.

Deployment receipt: `059fcba0-736e-474d-aad0-2fc83b268438`.
Returned boot: `c4ddcb8d-b573-47ba-a43b-ab1b5c179c9a`.
FIT SHA-256: `c7245f4e8f5f0045c780dae46402375c143ea31ad2d08014a1670af9dac37703`.
No FPGA rebuild was required; this uses the previously verified frozen image.

## Why the initial visit was refused

After configuration and calibration, the parent was still in epoch zero.
Its native snapshot contained historical boot/calibration drops. The original
visit preflight required zero drops even before the first real-refill REBASE,
so it returned source error `-2` before creating either child visit directory.
The operator retained the failure, verified unchanged image/boot identity and
fixed receive settings, and removed its own temporary files. No capture buffer
was opened by the probe and no native measurement was submitted.

The existing finite probe already distinguishes initial counters from active
acquisition counters. The visit parent now follows that distinction: it
retains and permits nonzero counters only in epoch zero, while capture is
disabled and tracking is drained, cleared and fault-free. Every nonzero
acquisition epoch still requires zero CDC/pacer drops. A real refill and
REBASE establish the child's new epoch. No counter is erased or reinterpreted
as a successful acquisition measurement.

The corrected independent sequence reviewer records the initial counters
separately and allows them only before the first child's acquired epoch. It
continues to require exact retained snapshot association and zero drops in
all subsequent epochs. Child source/IQ/arithmetic review remains separate.

## Tests and corrected physical result

Firmware-worktree commit `56ebc20955b88fd16579defcb75e233de5720aef` passes
**182 tests**, with zero failures, errors or skips. These include 42 new
rate/epoch/source-state cases, the visit controller and actual child-process
lifetime tests, and the existing live-probe integration tests. The new cases
exercise epoch 0 and nonzero epochs at both 30 and 60 MS/s, retaining the
rejections for active, faulty, configured, unread or mismatched-rate states.
Six additional operator-plan checks verify rate/channel selection and refusal
before radio contact for unsupported or duplicate plans.

The corrected Cortex-A9/NEON binary builds with warnings treated as errors.
SHA-256: `360d81ee27bb30b0f350e2d6e56f587895ab34c84e61e58d5fc0c15f4110007e`.
The first corrected retry receipt is `admission_refused`, with zero RF samples
because another radio's acquisition process held the shared global lease.
After that process exited, the corrected binary executed on the radio under
the normal leases. The completed run is `two-frequency-visits30-v3`.

| Visit | Native rate | ARM IQ rate | RF duration | Acquisition attempts | Handoffs | Active CDC/pacer drops | Maximum refill gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CH1 upper, 1,190,312,500 Hz, epoch 1 | 30 MS/s | 2.5 MS/s | 10.0663296 s | 6 | 0 | 0 / 0 | 7.316802 ms |
| CH2 upper, 1,440,312,500 Hz, epoch 2 | 30 MS/s | 2.5 MS/s | 10.0663296 s | 6 | 0 | 0 / 0 | 7.990962 ms |

Independent review passes all 3,072 capture-buffer checks, exact retained-IQ
associations, 439,956 acquisition-grid values and 96 moment/dense fits. The
parent's six transition records match their retained snapshots exactly and
bind to the child epochs. The initial epoch-zero counters remain recorded as
0 CDC and 5,413,144 pacer drops; both acquired epochs have zero drops.
Neither visit accepted a past observation or submitted a native measurement,
so this run verifies scanning and retuning, not physical tracking or feedback.

The radio's last verified state is the 30-MS/s image, CH2-upper LO
1,440,312,500 Hz, 2.5-MHz bandwidth, manual gain 30 dB, `A_BALANCED`, and TX
disabled. Image and boot identity are unchanged across the run, and temporary
files were removed. Sustained tracking, adaptive revisits, continuation after qualified
native loss and precision refinement remain incomplete.

The [evidence manifest](figures/2026_09_13_radio20_30ms_visit_readiness/evidence.json)
contains the successful deployment result, initial refusal, corrected retry
refusal, test results, binary hash and review/operator source hashes. Firmware
changes are local commits in the isolated firmware worktree; report publication
does not imply that firmware branch was pushed.

The separate [completed-run manifest](figures/2026_09_13_radio20_30ms_visit_readiness/evidence-completed.json)
retains the operator receipt and passing child and transition reviews. Its
SHA-256 is `e5c2c8c4287c9d5108876601efcb904fd102c989d0583546b07e9163fc165887`.
The operator receipt's original `complete_review_pending` status is preserved;
the subsequent independent reviews establish the final result.
