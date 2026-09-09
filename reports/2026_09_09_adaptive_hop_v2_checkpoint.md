# Adaptive hop control: native V2 checkpoint

2026-09-09. **Concrete native implementation and offline tests are complete for
this checkpoint; deployment and the full adaptive scanner are not complete.**
No radio, RF, production service, firmware, FPGA or kernel was accessed/changed.

## Implemented

- Separate HOPR/HOPS/HOPT V2 codecs retain policy settings and per-hop decisions.
  Existing V1 wire codecs are unchanged. Legacy readers reject adaptive records;
  the V1 session continues to require fixed ordering.
- The userspace scheduler now has an explicit V2 entrypoint that selects a
  target after the prior dwell deadline, validates the recall receipt and
  records the actual preceding/current targets. Existing dwell guards, finite
  capture accounting and restore lifecycle remain in use.
- A 32-entry lock-free SPSC queue connects a single acquisition-owner producer
  to the native policy on the hop thread. It applies bounded work per decision,
  preserves source bindings, rejects epoch changes and latches equal scanning
  on invalid feedback/overflow. It does not call a worker or wait for results.
- An additive native `commit_actual` port keeps shadow observations, visit ages
  and allocation credits attached to the target actually sampled. Proposed and
  actual targets remain separate in the V2 record. No unsampled RF is invented.

The synthetic integrated test runs the real native policy, feedback adapter,
threaded userspace scheduler and V2 session validator. Its detections are
synthetic and become available only after their original dwell ends. This is
not yet the GLRT-worker/provider-to-adaptive-OPENM path.

## Verification

| Check | Result and scope |
| --- | --- |
| Policy + frame conversion | 380 Python tests pass, including 296 native policy tests |
| SDK/worker regression | 194 tests pass, including positive-only feedback and existing SDK paths |
| Native policy adapter | 458,752 mask decisions, both rates and modes; additional fault cases |
| Concurrent feedback | 4,000 decisions with separate producer/consumer threads |
| ASan/UBSan/leaks | Legacy protocol/session/scheduler, new V2 core, native integrated path and policy adapter pass |
| ThreadSanitizer | Native policy adapter, including the two-thread handoff, passes with no diagnostics |
| CMake targets | All six legacy/new hop test targets build and run successfully |
| Provider fixtures | Fresh unqualified and positive-only provider builds/runs pass |
| Actual network regressions | 16 per profile, 32 executions; includes accelerated 300 s counter spans at both rates |
| Configuration | 16 GLRT build-configuration tests pass |
| ARM cross-build | Integrated native scheduler/session and policy test executables compile for Cortex-A9; not executed on ARM |

The network fixtures retain zero RX1/constant RX0 and do not negotiate adaptive
V2. They establish legacy transport regression coverage, not positive-signal
sensitivity, adaptive network behavior or unchanged live duty. No scientific
fixture, detector operating point, dwell length or RF setting was changed.

One build invocation failed because a newly added CMake target was requested
before regenerating the cached build tree. Explicit configuration followed by
build/run passed; the original error is retained. No test was weakened.

## Next required implementation

1. Compose V2 in the real userspace device/provider: capability negotiation,
   strict positive-profile/generation binding, acquisition-owner SDK feedback
   copies, metadata capacities, final status, cancellation and ownership cleanup.
   Do not expose V2 through the unchanged kernel/FW provider.
2. Add PPU and Leo V2 decoders/actual-visit recording products and adapters, then
   activity/cooldown/allocation/revisit UI and time-based Doppler processing.
3. Run actual positive-IQ adaptive network tests, saved-data detector/scheduling
   quality evaluation and fresh 300 s integrated ARM producer tests at both
   rates. Prior worker timings are not qualification for this build.
4. Separately authorized bounded live canaries, compatible release/remote-main
   integration, opt-in deployment, operational verification and rollback check.

Remote bases were fetched. The Leo and libiio feature branches contain their
respective remote bases. PPU now has two additional independent remote-main
commits; its worktree was not modified here and needs reconciliation before its
next implementation step. No push or deployment occurred at this checkpoint.

Raw receipts and exact source/artifact hashes are under
`/tmp/leo-adaptive-hop-v2.7Q9B36`. The retained
[evidence index](evidence/2026_09_09_adaptive_hop_v2/index.json) contains compressed
non-IQ/non-executable build/test receipts and JUnit records. The libiio
`adaptive-hop-v2.md` documents the byte layouts and lifetime/ownership ports.
The libiio implementation is local commit
`2fd1f93d83654cefadc82c102ccb3eda8c7809d1`; it requires the additive
`leo_adaptive_commit_actual` SDK entrypoint included with this Leo checkpoint.
