# Radio .20: continuing frequency visits after clean tracking loss

The corrected ARM two-frequency supervisor has now executed on radio `.20`.
Independent source, retained-IQ, arithmetic and transition checks pass for a
bounded 30-MS/s CH3/CH4 run. Both visits finish early when acquisition work
completes. Neither hands off to native tracking, so **continuation after
physical clean tracking loss remains unqualified**. The implementation and
its independent loss reviewer pass 217 focused tests.

Previously the finite child used the same failure exit for clean loss and
operational errors. The first correction added a distinct outcome but missed
the full-IQ dispatch path: worker completion was observed only for selected-IQ
capture. That made the new outcome unreachable in the actual visit profile.
Review caught this before deployment. The corrected visit mode observes full-IQ
worker completion; standalone behavior is preserved. The new tests exercise
that profile at both rates, using the actual threaded worker and simulated
native ports.

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

All **217 focused tests pass**, covering both rates, actual threaded native
loss/reacquisition with simulated ports, real fork/wait and signal handling,
and failure injection at frequency-transition boundaries. New checks verify
that clean-loss continuation still refuses busy hardware, unchanged epochs or
counters, changed RF settings, failed evidence retention, expired deadlines
and unknown child exits. The Cortex-A9/NEON build passes with warnings treated
as errors. These tests do not substitute for a physical handoff/loss/retune.

Corrected firmware commit: `dd422e0996770d564d6b70558d324265ac9fe681` (local firmware
worktree; not pushed by report publication).
ARM binary SHA-256:
`dca73d4861f67327f352f89f1cc2d74e6c8c73788dc471cf340502aeab84e53b`.
The [retained test results](figures/2026_09_13_radio20_clean_loss_visits/two-frequency-loss-review-tests-v3.xml)
and [correction patch](figures/2026_09_13_radio20_clean_loss_visits/component-v5.patch)
make the change reviewable independently of the firmware worktree.

The first full-suite run alongside CPU-heavy saved-IQ review had one simulated
60-MS/s native deadline failure (214 tests passed). A sequential rerun passed
215 tests; after the full-IQ dispatch fix, the final suite passed all 217.
The failed run remains retained. The independent loss reviewer verifies
native drain/clear, exhausted support horizon and observer join; mutation
checks reject altered terminal/join evidence. Saved CH1/CH2 IQ and transition
review also passes and rejects a false clean-loss label. Numerical and source
checks remain separate requirements.

## Corrected physical run

`two-frequency-visits30-clean-loss-v1` ran the corrected binary under the normal
global and serial leases. The FPGA image was unchanged. The exact serial is
`1040005e0b100007100010000bf33a5d4d`, boot
`c4ddcb8d-b573-47ba-a43b-ab1b5c179c9a`.

| Visit | Native / ARM IQ rate | Returned blocks | Exported RF duration | Attempts / handoffs | Active CDC/pacer drops | Maximum refill gap |
| --- | --- | ---: | ---: | --- | --- | ---: |
| CH3 upper, 1,690,312,498 Hz, epoch 3 | 30 / 2.5 MS/s | 1,090 | 7.1450452 s | 6 / 0 | 0 / 0 | 6.764298 ms |
| CH4 upper, 1,940,312,500 Hz, epoch 4 | 30 / 2.5 MS/s | 1,153 | 7.5579652 s | 6 / 0 | 0 / 0 | 7.917636 ms |

The total is 14.7030104 seconds of exported RF. All 36,749,312 returned IQ
samples are retained. Intentional early shutdown leaves 4,053 and 4,161
exported samples unreturned at the two tails; those 8,214 samples are outside
the retained stream and cannot be reviewed. The original reviewer flag that
claimed full exported-IQ retention was corrected in separate v2 results,
preserving the original results and their hashes. All acquisition/worker cuts
are independently associated with the retained returned stream.

Both visits report zero accepted past observations and no native results.
Source, grid/order/resolver, dense-fit and parent-transition checks pass.
The radio ends at CH4 upper with the same 30-MS/s image, TX disabled, fixed
receive settings verified and temporary files removed. The new ARM binary
was staged for this bounded test; this is not a persistent tracking service.

The [completed evidence](figures/2026_09_13_radio20_clean_loss_visits/evidence-v5.json)
retains the operator, amended child reviews, sequence review and test results.
Its SHA-256 is `19f73e5a6edad3c59124d1796aea8252bc336c38dfc8e845f371ac7541f3f993`.
The earlier [CH1/CH2 result](2026_09_13_radio20_30ms_visit_readiness.md) remains
historical evidence. Sustained tracking, physical clean-loss continuation,
adaptive revisits and precision refinement remain incomplete.
