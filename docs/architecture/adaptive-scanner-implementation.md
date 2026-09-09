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
   A follow-up connects the same native TCP-produced durable recording to its
   read-only history/detail/GLRT HTTP APIs, without replacing its manifest.
   All 12 rate/mode/ending cases pass against a fresh protected positive-only
   provider build: four full 300-second counter spans, four mid-capture cancels
   and four pre-refill cancels. Exact epochs, source span/duty, actual targets,
   retained versus started inventory, source-bound classifier evidence, HEAD
   responses and legacy-route separation are checked. The related selection
   passes 68 scheduling/storage/API and 69 UI tests. This is accelerated
   constant-RX0/zero-RX1 localhost traffic and ASGI/component testing, not a
   rendered deployed browser, positive-signal sensitivity or live-duty proof.
   The first local fixture attempt was correctly rejected because its newly
   generated templates were group-writable; the recipe now sets 0600. No SDK
   trust check, runtime behavior, scientific fixture or threshold was changed.
   Failed and passing receipts and source/build hashes are retained in the
   [publication API evidence](../../reports/evidence/2026_09_09_scanner_publication_api/index.json).
7. **Runtime/quality:** qualify the exact integrated build on held-out saved IQ,
   simulate/shadow scheduling without inventing unsampled RF, and run full
   300-second ARM modeled-producer tests at both rates. Existing older replay
   passes are not passes for this new SDK/policy/package. Preserve captured IQ
   and complete result accounting, with overload skips explicitly UNKNOWN; no
   unbounded backlog, shortened dwell or silent every-Nth substitution.
   The SDK replay now has an explicit positive-feedback research mode. It
   checks independent, source-bound scheduling observations alongside immutable
   wire results, including consumer ordering and timing. This does not itself
   exercise the scheduler thread, bounded queue, adaptive choices or IIO load.
   See the [feedback replay checkpoint](../../reports/2026_09_09_scanner_glrt_feedback_replay_checkpoint.md).
   A subsequent research shadow adapter now connects the real SDK, libiio SPSC
   queue, policy and scheduler thread through public ports with mocked hardware
   IO. Positive-rich saved RX1 workloads pass full elapsed 300-second desktop
   runs at both rates: 2,479 results/observations/choices each, with independent
   policy-model agreement. These repeated development sequences do not demote
   any target; separate generated-pilot/zero-IQ integration tests exercise
   weighted proposals. This is not held-out quality, executed adaptive RF,
   IIO/network contention, physical queue occupancy or live-duty qualification.
   1,009 portable tests and five explicitly marked libiio integration tests
   pass; short ASan/UBSan/leak checks and ARM cross-builds pass. ARM execution
   remains paused on the intended spare's changed SSH host key, before any
   upload or remote execution. Trusted identity confirmation, exact-package
   ARM load/memory tests and independent quality remain open.
   See the [threaded shadow checkpoint](../../reports/2026_09_09_scanner_threaded_shadow_checkpoint.md).
   The user subsequently confirmed per-boot SSH key rotation. Strict checking
   remains enabled with a task-local current-boot pin; the exact idle spare was
   reidentified by USB/LAN serial. Both full 300-second ARM shadow replays now
   pass, 2,479 results/observations/choices each with independent numerical and
   policy parity; maximum consumed feedback age is 242 ms. Worker wall p99 is
   68.98/115.86 ms at 2.5/5 MS/s; 5 MS/s headroom remains a concern. All temporary
   remote files were removed after verified cleanup; installed-library hashes
   are unchanged. This uses mocked acquisition/recall, not the full installed
   provider, live duty, or an independent quality holdout. ARM weighted/fault
   transitions, precise queue occupancy and full-package memory remain open.
   See the [ARM threaded checkpoint](../../reports/2026_09_09_scanner_threaded_arm_checkpoint.md).
   Capture-first protection is now an additional, default-off SDK/provider
   opt-in: two-slot admission, 250 ms oldest-job shedding, a 500 ms owned-worker
   watchdog, callback/source-gap pressure and four healthy blocks to resume.
   Skipped evidence remains unhealthy UNKNOWN; recovery does not unlatch the
   capture-long uniform fallback. New desktop overload, policy and actual
   provider tests qualify these paths, not new ARM timing or live duty. The
   previous ARM receipt predates this implementation and cannot qualify it.
   See the [capture-protection checkpoint](../../reports/2026_09_09_scanner_capture_protection_checkpoint.md).
   Subsequent protected 300-second ARM saved-IQ replays now pass at both rates:
   2,479 results/observations/choices each, with two explicit unavailable checks
   at 5 MS/s and none at 2.5 MS/s. Forced-pressure runs verify recovery without
   treating unknown as a miss or unlatching uniform fallback. These still mock
   acquisition and retunes; they are not live-duty measurements.
   A frozen independent 192-dwell RF split flags 61/64 and 46/49 full-reference
   supported dwells at 2.5/5 MS/s. These are reference-relative observations,
   not satellite truth or a measured false-alarm probability.
   The exact updated protected userspace package also passes ARM loader,
   saved-IQ SDK/policy and production staging/cleanup checks, without opening an
   IIO context. The candidate was removed afterward; it is not deployed.
   See the [protected ARM](../../reports/2026_09_09_scanner_protected_arm_checkpoint.md),
   [RF holdout](../../reports/2026_09_09_scanner_rf_dwell_holdout.md) and
   [exact package](../../reports/2026_09_09_scanner_protected_package_checkpoint.md)
   evidence. Live streaming, adaptive allocation benefit, analysis throughput,
   deployed UI, remote merges and operational restoration remain open.
8. **Live/release:** separately authorized <=30 minute canaries, first fixed
   detector off/on, then adaptive versus fixed with detector enabled in both.
   The proposed combined matrix reuses the fixed detector-on comparison:
   fixed/off, fixed/positive-only and adaptive/positive-only at each rate are
   six 300-second captures, 30 minutes total RF. Authorization for this specific
   matrix on spare `winbond-db620818a328172c` at `192.168.1.14` remains pending.
   Hardware identity/ownership, physical LAN and all serial exclusions are mandatory.
   Verify source-counter duty, IQ continuity, transitions, final inventory and
   cleanup; review compatible releases, merge, deploy opt-in, verify rollback.

   Use the existing scheduled application capture path and its real acquisition
   authority and owned iiOD lifecycle. The older standalone
   `run_persistent_hop_durable_canary.py` does not expose detector options or
   adaptive capture and cannot qualify the on/adaptive conditions unchanged.
   Keep gain, IF/bandwidth, 120 ms valid dwell, guard, block size, kernel buffers,
   read-ahead and storage queue identical across conditions at each rate. Freeze
   the reviewed live guard explicitly; a canary's 1 ms default is not evidence
   of the currently deployed guard. Do not wait on six 20-minute scheduled slots
   or start a background radio campaign to execute this bounded matrix.

   For each actual recording, fully verify IQ through its owning store, then
   read its history, detail and classifier publication through the public API.
   Adaptive recordings use `/api/v1/scanner/adaptive-sessions`; legacy fixed
   recordings retain their separate routes/contracts. Check mode, manifest
   identity, exact counters, source span, started versus retained visits and
   explicit unavailable detector outcomes before examining browser rendering.
   Do not treat successful fixture APIs as deployed-browser verification.

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
