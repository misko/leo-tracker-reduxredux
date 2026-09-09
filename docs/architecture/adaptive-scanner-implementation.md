# Adaptive single-RX scanner: execution checkpoints

2026-09-09. User-authorized implementation, tests, deployment and verification.
This document tracks the full requested outcome, not a release pass. New RF
collection still requires explicit bounded authorization. Fixed scanning remains
the default. Scanner development does not require custom firmware, kernel or
FPGA changes. A separate explicit operator request authorized stock-release
flashing and 2R2T restoration on `.18`, documented below.

## Current operator hardware restriction

The operator has withdrawn `192.168.1.14` / `winbond-db620818a328172c` from this
task: it is in use by another agent and is not currently visible over local USB.
Do not connect to, probe, run tests on, stop processes on, or reclaim that radio.
Historical qualification receipts and temporary access recipes are evidence of
past runs, not permission to reuse it.

Any replacement must be physically connected to this host over USB and currently
enumerated with its exact serial. Verify that serial's physical `192.168.1.*`
Ethernet mapping and availability/ownership before use; all capture and test
traffic must use that Ethernet interface. A historical USB mapping is insufficient.
The original excluded serial `104000bac4950008230026001b440a003a` remains excluded.
The operator subsequently authorized `.18` for the six 300-second capture
matrix. Its exact serial `1040007c4a94000211000b009186843ef2` currently enumerates
at USB `3-11`, and its physical Ethernet identity was verified read-only.
Its earlier `v0.50-plutoplus-starlink-pss-15m-rx-only-dnm-v7` image exposed only
one complex receiver and lacked the DDS device expected by pyadi. The operator
then explicitly authorized flashing the latest published release and restoring
2R2T using PPU. This completed on `v0.49-plutoplus-spf-iq-direct-async-v4`:
AD9361-compatible 2R2T, four RX storage elements, ABI 3, 216 MiB CMA, safe TX
and exact QSPI readback verified. Stock release firmware/FPGA contents changed;
the bootloader did not. No RF capture was started. The layout blocker is resolved,
but exact-package live capture, duty and deployment gates remain open. Do not
infer further flash authority or silently record only one RX.
See the [restoration checkpoint](../../reports/2026_09_09_radio18_v49_2r2t_checkpoint.md).
The other currently USB-visible spare is `winbond-db6968136727402c` at `3-7`;
its historical `.152` mapping did not return a radio identity. Its current LAN
address and availability remain unconfirmed; it has not been authorized for RF.

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
   A later read-only spare preflight exposed a host packaging gap: the previous
   ABI-3 installer cannot select the GLRT-capable library. PPU now has an
   explicit `--scanner-glrt` install option pinned to the exact `a1088b6` native
   source, preserving old defaults and receipt schema. A fresh isolated wheel
   installation and clean-process verification pass, along with 834 component
   and regression tests. The production staging/inventory pin is deliberately
   unchanged; release promotion remains open. The installed runtime confirms
   `.18`'s then-existing hardware-layout blocker rather than bypassing it.
   Subsequently authorized PPU stock-release maintenance resolved that blocker
   with verified v0.49/2R2T; it did not run RF or qualify the live scanner.
   See the [host runtime and USB preflight checkpoint](../../reports/2026_09_09_scanner_host_runtime_checkpoint.md).
8. **Live/release:** separately authorized <=30 minute canaries, first fixed
   detector off/on, then adaptive versus fixed with detector enabled in both.
   The proposed combined matrix reuses the fixed detector-on comparison:
   fixed/off, fixed/positive-only and adaptive/positive-only at each rate are
   six 300-second captures, 30 minutes total RF. The proposed `.14` target is
   withdrawn under the current operator restriction above. A replacement must
   satisfy current local USB attachment, exact serial/LAN mapping and ownership
   checks, and receive explicit bounded RF authorization before this matrix runs.
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

   **Latest live checkpoint:** the bounded `.18` matrix and startup diagnostics
   are stopped, with a conservative enclosing-time upper bound of 1,660 of
   1,800 authorized seconds used. Userspace first-accepted-IQ activation and
   source-backlog admission fixes are committed locally. The exact revised
   bundle completed 300-second fixed/GLRT-on 5 MS/s and adaptive/GLRT-on 2.5 MS/s
   scans at 94.4688% and 94.1583% duty, with full-IQ verification and real-store
   API checks. Screening coverage was 26.63% and 100%, respectively. These are
   not matched no-regression passes; no qualifying positives were found, so
   real-signal adaptive weighting/cooldown benefit is still unverified. Further
   full-length RF tests need additional authorization. No remote merge or
   deployment is claimed. See the
   [live checkpoint](../../reports/2026_09_09_radio18_live_startup_checkpoint.md).

   **Host release staging:** an explicit raw-stager `--scanner-glrt` option and
   exact additional native-source inventory validation are implemented locally,
   retaining default behavior and the existing sealed receipt layout. It does
   not enable scanning or replace the ARM bundle. Current locked PPU still
   predates the option, and libiio/PPU dependency promotion, lockfile updates,
   companion packaging, qualification and deployed verification remain open.
   See the [staging checkpoint](../../reports/2026_09_09_scanner_release_runtime_checkpoint.md).

   **ARM release asset:** the exact latest live-tested bundle is now packaged
   separately from the legacy daemon, with all 12 files in the checked external
   release inventory. Actual-byte integrity/mode/negative tests and real PPU
   companion shell operations on a local fixture filesystem pass; no radio or
   ARM code was executed for this packaging step. This preserves tested bytes,
   not a claim of bit-reproducible cross-compilation. Dependency promotion/pins,
   full isolated release build, remaining quality/duty/adaptive RF gates and
   deployed verification still remain. See the
   [bundle checkpoint](../../reports/2026_09_09_scanner_bundle_release_checkpoint.md).

   **Frozen release build:** the dependency candidates are now published on
   their feature branches, and Leo pins PPU `6b577ac...` consistently. A full
   frozen, non-editable release at `06c1fd88...` was staged and sealed with the
   exact scanner host runtime and unchanged ARM bundle. Repeat validation,
   314 installed-package scanner tests and 139 web tests pass. Production
   selectors/services are unchanged. Hosted Python 3.11 has the same three
   paired-capture failures on PPU main and the candidate; local reproduction
   passes, so that failure remains unresolved rather than waived. Main merges,
   activation, deployed verification and the outstanding live/scientific gates
   remain open. See the
   [frozen-build checkpoint](../../reports/2026_09_09_scanner_frozen_release_checkpoint.md).

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
