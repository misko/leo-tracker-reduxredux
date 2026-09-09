# Adaptive single-RX scanner: execution checkpoints

2026-09-09. User-authorized implementation, tests, deployment and verification.
This document tracks the full requested outcome, not a release pass. New RF
collection still requires explicit bounded authorization. Fixed scanning remains
the default; no firmware flash, kernel or FPGA change belongs to this work.

## Policy frozen for the first implementation

- Eight independent targets: CH1L..CH4L, CH1U..CH4U. Do not suppress an upper
  target because the corresponding lower target was missed.
- Begin each capture with three uniform visits per target. Reset between scans.
- One positive promotes immediately and resets misses. Demote only after three
  consecutive successfully evaluated misses AND two seconds since the most
  recent positive's source-dwell end. An unknown breaks the miss streak.
- Smooth deterministic weighted round-robin, active:quiet = 3:1. Unobserved
  targets retain exploration priority. Without any active target, scan equally.
- Reserve exploration before a nominal three-second revisit deadline; a
  conservative 160 ms hop planning budget is initially used. Actual hardware
  lateness remains recorded and must be measured, not hidden as a guarantee.
- Initial feedback age limit: one second from the original valid-dwell end.
  Source-order application, exact source binding, no duplicate refresh.
- Three consecutive unhealthy/missing/expired results, or an explicit feedback
  fault, latch equal scanning until the end of this capture. Healthy but
  fractionally incomplete estimation is unknown, not a worker-health failure.
- Preserve 120 ms valid dwells, 300 s captures, 1,200 s cadence, both recorded
  receivers, RX1-only classification, rate allocation, bandwidth/IF and guards.

The extra feedback age/health/hop-budget values are engineering defaults for
offline qualification. Freeze any measured adjustment before holdout/canary;
do not silently change user-facing three-miss/two-second behavior.

## Checkpoints and current state

1. **Baseline:** dedicated existing feature worktrees fetched remote main/master.
   Leo and libiio already contain their remote base. PPU's two newer independent
   main changes were merged without conflicts. No unrelated worktree changed.
2. **Decision and pure policy:** implemented native deterministic policy with
   no IIO/worker/storage imports; 294 initial tests pass. Includes all 256
   activity masks, both rate-specific cooldown boundaries, 30/30/30/10 example,
   source-order results, starvation protection, expiry and fault fallback.
3. **SDK decision/feedback:** additive positive-only open and independent
   observation reader implemented. Original open/config and persisted GLRT
   layouts are unchanged. A completed bounded miss remains unavailable in the
   original frame, with a separate scheduling hint, never NO_SIGNAL. Latest
   worker/SDK/host tests pass 222 cases across all seven worker variants,
   including both positive and unqualified host paths at both rates.
4. **Provider/host/UI positive profile:** explicit `positive-only-v1` profile
   wired in source, default unqualified/disabled unchanged. Existing extensible
   session mode field is used without changing persisted major-v1 contracts.
   Host, publication binding and UI reject absence claims in this profile.
   Both real provider builds pass; each profile passes 16 loopback tests,
   including accelerated 300-second counter spans at both rates. Positive RF
   fixtures through the actual SDK/PPU host and zero-IQ network fixtures are
   separate tests, not a full positive-signal network/load qualification.
   Portable Leo tests pass 500, web tests 106 plus build, PPU tests 299, and
   libiio configure tests 16. This is not yet deployment qualification.
5. **Adaptive hop mode and complete recording:** native core, real provider and
   PPU stream/client/backend composition now pass offline tests. Explicit V2
   OPENM, capability/pinned-policy admission, userspace factory, acquisition-owner
   SDK feedback and final drain/cleanup are connected. Host reconstruction keeps
   actual visits, shadow proposals, source-time decisions, bounded dual-RX IQ
   and cancellation accounting. Four accelerated full-300-s rate/mode network
   cases pass; these use synthetic zero RX1, not positive RF or ARM load.
   Existing V1 fixed-order contracts remain strict. Leo now has separate
   application adaptive schema-V1 kinds (wire V2 remains explicit), actual-visit
   IQ storage, bounded queued compression, lifecycle orchestration and a strict
   PPU V2 mapping boundary. Original and new manifest kinds are not conflated.
   Full-300-s synthetic TCP-to-store verification, short cancellation and
   pre-refill cancellation are covered. The concrete single-owner adaptive radio
   adapter and scheduled opt-in now compose capture, authority/cleanup, queued
   IQ publication and separately source-bound classifier publication. Retry
   checks preserve mode, identity and failed staging without recapturing a slot;
   the durable supervisor distinguishes capture health from detector quality.
   Both rates/modes pass full scheduled synthetic TCP-to-store/result tests,
   cancellation and pre-refill cancellation. Adaptive history/UI is covered by
   checkpoint 6 below; actual-time analysis remains pending. Do not feed adaptive
   receipts to the fixed writer or call eight visits a sweep.
   See the [scheduled runtime checkpoint](../../reports/2026_09_09_adaptive_scheduled_runtime_checkpoint.md).
   See the [application recording checkpoint](../../reports/2026_09_09_adaptive_recording_checkpoint.md).
   See the [provider/host checkpoint](../../reports/2026_09_09_adaptive_provider_host_checkpoint.md)
   and [native hop checkpoint](../../reports/2026_09_09_adaptive_hop_v2_checkpoint.md).
6. **Analysis/UI:** adaptive/shadow history, actual-visit timeline, allocation and
   revisit/unobserved metrics, cooldown/choice inspection and independently bound
   GLRT evidence are now integrated locally into the API and React scanner UI.
   Source epochs remain exact decimal strings; empty source spans are unavailable,
   and incomplete starts are distinct from retained IQ. Production-composition,
   old/new selection and full-300-s metadata tests pass. The pure actual-visit
   fractional analyzer, pinned source reader, immutable visit checkpoints,
   bounded resumable service and opt-in CLI are now implemented. Four saved RX1
   rate/edge cases pass direct numerical parity and real codec/CLI/resume/metrics
   publication; metadata, RX0 and additional fixture visits are explicitly
   synthetic. The new checkpoint passes 674 component/regression tests. These
   are dense metrics. Actual-time coverage, fractional-response and all-passed
   CFO PNGs, explicit candidate-only associations, restartable overview generation,
   and additive read-only progress/artifact API/UI are now integrated locally.
   Final overview checks pass 718 Python and 139 web tests plus build; six saved
   RX1 cases exercise codec/CLI/API and four full-span synthetic projections
   preserve maximum candidate inventories. A separate 806,432-candidate synthetic
   store/render stress verifies bounded processing. Passed-only association
   fitting uses an explicit configured margin gate; it cannot estimate a negative
   tail from filtered input. These associations are not L/U or cross-channel
   joins, satellite IDs or track-quality qualification. Deployed browser
   verification remains. Dense smoke timings expose a serial throughput gap;
   do not automatically dispatch full dense scans every 20 minutes or silently
   substitute sparse coverage before measuring/addressing it.
   See the [history/UI checkpoint](../../reports/2026_09_09_adaptive_history_ui_checkpoint.md).
   See the [fractional metrics checkpoint](../../reports/2026_09_09_adaptive_fractional_analysis_checkpoint.md).
   See the [overview/API/UI checkpoint](../../reports/2026_09_09_adaptive_overview_checkpoint.md).
7. **Runtime/quality:** qualify the exact integrated build on held-out saved IQ,
   simulate/shadow scheduling without inventing unsampled RF, and run full
   300-second ARM modeled-producer tests at both rates. Existing older replay
   passes are not passes for this new SDK/policy/package. No loss/backlog or
   shortened dwell/every-Nth substitute for the requested behavior.
8. **Live/release:** separately authorized <=30 minute canaries, first fixed
   detector off/on, then adaptive versus fixed with detector enabled in both.
   Each two-rate A/B matrix is four 300 s captures (20 minutes RF). Hardware
   identity/ownership, physical LAN and all serial exclusions are mandatory.
   Verify source-counter duty, IQ continuity, transitions, final inventory and
   cleanup; review compatible releases, merge, deploy opt-in, verify rollback.

## Evidence discipline

Current raw build/test work is under `/tmp/leo-adaptive-glrt.VkIAkP`. A fresh
desktop configure first failed because optional Avahi development dependencies
were absent. The localhost-only fixture disables DNS-SD; nothing was installed.
A later link exposed CMake guessing `-lsdk` for an explicit `sdk.so` path.
An imported target now links the exact artifact. Threshold configuration tests
also guard against ambiguous C integer literals; integer-looking decimal values
are emitted as floating literals. Initial configure-test fixtures incorrectly
disabled local/XML backends required by iiOD; their prerequisites were corrected,
not bypassed. Failed receipts are retained separately from passing retries.

ASan/UBSan/leak-checked policy stress passed 1,280,000 choices (both rates, all
256 masks, 2,500 visits each). The policy stress executable cross-compiles for
Cortex-A9 ARM; it was not executed on a radio. Existing web canvas/dependency
deprecation and bundle-size warnings remain visible, not represented as failures
or hidden. No scientific fixture or detector numerical threshold was changed.

Record exact source/artifact hashes, commands, JUnit counts, numerical/timing
limits and failures at the next checkpoint. Passing policy tests or positive
transport is not detector sensitivity qualification or unchanged live duty.
Production services/radios have not been accessed or changed by these steps.
