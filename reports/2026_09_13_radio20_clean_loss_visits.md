# Radio .20: continuing frequency visits after clean tracking loss

The ARM two-frequency supervisor can now continue after a specifically proven
native acquisition loss. Previously it stopped because the finite child used
the same failure exit for clean loss and operational errors. This is a tested
implementation change; it has not yet been physically exercised or deployed.
No new RF was collected for this change.

The standalone probe keeps its existing exit semantics. Within the visit
composition, the child returns a distinct exit 3 only after its worker and
observer have joined, the native controller has retained and popped every
configured head, loss recovery has drained and cleared the controller, all
paired IQ is retained, and final capture/source and file cleanup succeeds.
Cancellation, ordinary acquisition errors and cleanup failures cannot produce
this outcome. The parent retains it as result 1 on the `after_run` transition,
then checks idle hardware, fixed RF settings, epoch/counter advancement,
retention and the global deadline before another tune.

Both visits remain bounded by the existing 60-second parent deadline and
maximum 20.1326592 seconds of RF. FPGA/native measurement rates remain 30 or
60 MS/s; ARM acquisition and the passive observer use 2.5-MS/s IQ. Native
acceptance gates, precision claims and standalone persisted results are
unchanged. The new disposition denotes loss, not a successful tracking lock.

## Validation and limits

All **215 focused tests pass**, covering both rates, actual threaded native
loss/reacquisition with simulated ports, real fork/wait and signal handling,
and failure injection at frequency-transition boundaries. New checks verify
that clean-loss continuation still refuses busy hardware, unchanged epochs or
counters, changed RF settings, failed evidence retention, expired deadlines
and unknown child exits. The Cortex-A9/NEON build passes with warnings treated
as errors. These tests do not substitute for a physical handoff/loss/retune.

Firmware commit: `a8535dac0b139221dbf37acc2414bc4190d97377` (local firmware
worktree; not pushed by report publication).
ARM binary SHA-256:
`6f8884879c4ee8f9b731fc4687d79b637bcb141cb32e4bb73a5260abd18de149`.
The [retained test results](figures/2026_09_13_radio20_clean_loss_visits/tests.xml)
and [component patch](figures/2026_09_13_radio20_clean_loss_visits/component.patch)
make the change reviewable independently of the firmware worktree.

The [last physical two-frequency run](2026_09_13_radio20_30ms_visit_readiness.md)
remains the authoritative radio result: serial
`1040005e0b100007100010000bf33a5d4d`, 30-MS/s image, CH2 upper, TX disabled.
It had no handoff and therefore provides no evidence for clean-loss
continuation. Before deploying this binary, the physical evidence reviewer
must explicitly validate the new disposition against retained native loss,
observer join, final source state and the subsequent visit. Sustained
tracking, adaptive revisits and precision refinement remain incomplete.
