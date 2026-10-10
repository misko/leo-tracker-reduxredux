# Continuous scanner for eight channels with 20 ms IQ windows

## Shared automatic acquisition and history

The deployed Adaptive scans view merges the existing adaptive history and fast
capture status ports. Mode and edge remain explicit; fast captures retain their
own recording identity and immutable IQ/GLRT contracts. Selection uses
`scan_id=<recording-id>&scan_kind=fast`; existing adaptive links remain valid.
The existing tracking/association/positioning panel renders fast results through
the previously qualified TrackingInput adapter. There is no separate Fast scans
navigation tab in this deployment. `web/src/App.tsx` composes the shared history
and existing artifact panels; the reusable history and fast-detail components
also live in `web/src`.

`tools/run_shared_scan_cycle.py` composes one capture per invocation of the
existing `leo-v052-adaptive.service` and timer. The durable sequence is fast lower,
adaptive, fast upper, adaptive, repeating; each capture lasts 300 seconds. Adaptive
keeps its installed rate/edge policy. The normal timer retains its ten-minute gap
after each capture. Radio acquisition is sequential; numerical analysis may run
concurrently. An outstanding queue of three fast analyses defers acquisition.

Both modes claim the existing LocalCaptureAuthority under the existing pipeline
flock. The web Start/Stop buttons therefore govern both modes. Stop fences future
claims immediately and lets the current bounded capture restore the radio; it
does not cancel offline analysis. Failed acquisitions preserve the sequence slot.
Fast captures use the pinned, metadata-verified PPU provider, record 20 ms per RX
after the existing 20 ms guard, and publish checkpoints for the existing automatic
analysis service. No numerical algorithms or public persisted contracts change.

The pinned recorder/config release is `/opt/leo-shared-scans/20261010-r1`; the
selector is in `20261010-r2`, and the adaptive-format frontend is in
`20261010-r3`. The shared service drop-in is
`deploy/systemd/leo-shared-scan.service.conf`. Verification uses a separate config
with `maximum_attempts=3`, counting failures too, and a temporary 15-second timer
gap. That bounds new verification RF to 15 minutes even if the observer exits.
Restore the normal timer and config after qualification. Artifacts are under
`/srv/bulk/leo/shared-scan-qualification-20261010`.

The bounded live check completed fast lower (6,757 paired RX visits), adaptive
(2,186 retained of 2,199 planned visits), and fast upper (6,759 paired RX visits).
The fast captures had no invalid or skipped device windows; the adaptive capture
passed its existing 99% delivery gate. Acquisition intervals did not overlap.
All three appeared in one open browser without a reload. Both fast GLRT jobs
completed and entered the existing standard pipeline; adaptive GLRT started after
its larger IQ publication completed. At the rollout snapshot, downstream science
was still running: this verifies automatic admission and handoff, not completion
of every positioning stage. See `automatic-integration-verification.json` for the
explicit stage states. No new localization-accuracy claim is made.

Ten owned Python tests and 58 frontend tests passed, along with TypeScript/Vite,
lint, live shared Start/Stop, deep-link/back/reload, and new-trajectory image checks.
The bounded override was removed; the normal timer started its next adaptive
capture automatically at 03:35 UTC on 2026-10-10.

The r3 frontend uses the adaptive capture header, summary grid, GLRT panel, and
the existing `ScannerTrackingPanel`/`ScannerRefinementPanel` composition. Shared
trajectory, TLE, and positioning artifacts precede the collapsed fast-score
diagnostics. Artifact availability remains explicit: attaching the refinement
panel does not create an unpublished comparison or launch numerical work. No
adaptive dwell or phase evidence is synthesized from a fast report. All 72
relevant frontend tests passed; the live browser verified identical header/grid
formatting and 28 existing PNG artifacts. Evidence is saved under
`/srv/bulk/leo/shared-scan-formatting-20261010`. The capture timer, shared controls,
normal cadence, and automatic analysis service remain enabled.

Rollback: stop the capture timer and drain the current service, then remove only
`leo-v052-adaptive.service.d/zzzz-shared-scans.conf` and the API drop-in
`zzzzzzzzzzzzzzzzzzzzzzzz-shared-scans.conf`. Remove any temporary
`zzzzz-bounded-verification.conf` drop-ins under `/run/systemd/system`, reload
systemd and restart the API. The preceding adaptive acquisition and frontend
remain pinned and available; recorded IQ and analysis publications remain intact.

## Automatic publication qualification

The `leo-fast-scan-analysis.service` composition watches explicit continuous-run
checkpoints under `/srv/postgres-nvme/fast-scan-recordings`. It exposes recording
progress through `/api/v1/fast-scans/automatic`, waits for a successful terminal
receipt and durable IQ, then invokes the existing eight-worker GLRT queue. Its
verified `TrackingInput` export supplies the existing deployed `scanner_tracking`
CLI, including trajectory/TLE reviews, position methods, blind regional, adaptive
TLE positioning, and B7 regional analysis. The numerical components are unchanged.
The bridge resumes their checkpoints and checks every completion port before
publishing `complete`; failures remain visible. Analysis does not acquire RF.

Fast records in the Adaptive scans history refresh every ten seconds and use the
existing tracking and positioning panels. Completion describes execution and artifact integrity;
individual scientific products may explicitly abstain or report insufficient
evidence. RF labels retain their recorded LNB hypotheses. B7 outputs retain the
existing calibration arms; a separate same-stage B3/B4/B4W comparison records
matched c=0 versus fitted-c results before dynamic RF-time terms, with fit metrics
and reference position errors reported separately.

The bounded lower/upper/lower qualification uses three 300-second captures on
radio `.20`, at 2.5 MS/s, with 20 ms windows and 20 ms reported post-recall guard.
Its deployment receipt, live-browser transition log, and verification outputs
are under `/srv/bulk/leo/fast8-auto-qualification-20261010`. The source overlay is
pinned at `/opt/leo-fast-auto/20261010-r1`, with discovery hardening in the
`20261010-r2/worker/src` overlay; the API overlay preserves the previous
deployed API and web features. Adaptive RF capture was paused for that earlier
qualification; the shared schedule described above now runs both modes.

The first live qualification exposed a stale progress-counter snapshot in the
campaign producer. Its final sealed receipts remained valid. Discovery now
records invalid-checkpoint diagnostics per recording and continues processing
other runs, rather than terminating active analysis. A valid terminal receipt
is still mandatory. The producer now bounds reported captured windows below by
the writer's accepted count. Restarting the analysis service after GLRT sealing
resumes downstream checkpoints without repeating GLRT or touching RF ownership.
The service also requires `PrivateTmp=yes` with `ProtectSystem=strict`: the
existing track-review renderer uses temporary directories. The first live run
reported that permission failure truthfully; after correcting the sandbox its
standard job was returned to the automatic worker, retaining sealed GLRT and
completed satellite comparisons. No additional RF was acquired for either fix.
The existing prediction scratch namespace also needed explicit provisioning for
the service user. The unit now creates the standard output namespaces and
`prediction-scratch` before starting. The first job required two operator
requeues during these permission repairs; the other two required none.

All three runs completed the five standard downstream stages. Lower/upper/lower
captured 6,757/6,759/6,759 paired-RX visits with zero invalid captures. The open
browser observed all recordings appear without reload and reach complete;
final browser selection loaded each recording's own trajectory without JavaScript
errors. HTTP verification checked all 84 PNG artifacts against their hashes.
Component validation passed 29 Python tests and three UI tests, plus lint/build.

Position products remain diagnostic (`position_fix_claimed=false`). The matched
B4W c=0 to fitted-c comparisons gave frequency RMS 110.42 to 80.85 Hz, 131.63 to
77.80 Hz, and 97.32 to 77.24 Hz. Reference position error independently changed
694.79 to 979.52 m, 2,729.28 to 908.10 m, and 3,636.49 to 1,905.97 m. Thus improved
frequency fit did not consistently improve reference position error. These arms
share the upstream fitted-c calibration/association; they isolate the downstream
coefficient, not the entire calibration pipeline.

## Motivation

Implement a device-resident scanner that visits the configured eight targets in
order, captures exactly 50,000 complex sample times per receiver at 2.5 MS/s,
then repeats that order until an explicit stop request. The device owns every
recall and window boundary. The host starts, observes, records, and stops the
run; it does not command each visit. Compute immediate power from the saved IQ
and run GLRT offline. This workstream can ship independently of the proposed
FPGA power scanner.

## Problem

**Existing evidence and the missing behavior.** The
[current implementation](short-window-scan-implementation.md) already provides
exact windows, a bounded writer, hardware counter support, and offline replay.
The [measured runs](../../reports/2026_10_09_short_window/hardware-summary.json)
with a 20 ms transition allowance had median valid-start spacing of 40.231 ms
and 40.272 ms. First complete eight-target coverage took 15 and 33 visits,
respectively, because target selection was weighted. Equal weights and UNKNOWN
feedback do not produce an ordered sweep. Filtering repeated targets on the
host would discard evidence without changing the device schedule.

The verified device was firmware
`v0.60-plutoplus-spf-adaptive-native-fastlock`, serial
`104000b29905000e17000800065934759d`, reached through physical LAN READSCAN.
PPU source commit `0a07581ab2b60888d85ba6ca1d6c85065bf820e3` uses **protocol v1**
for fixed 20 ms at capability-negotiated 2.5 MS/s. The repository's separate
native policy copy defines a fixed-dwell version 4; that does not establish that
the measured PPU campaigns used v4. The existing PPU `ScanSetup` admits only
1–300,000 ms, and the session ledger is allocated from duration/dwell and capped
at 16,384 visits. Restarting five-minute campaigns would repeat preparation and
restoration and introduce acquisition gaps; it does not meet continuous mode.

## Solution

This is a proposed workstream, not an available continuous command or firmware
capability. It does not authorize external repository changes, flashing, or new
RF. Laboratory collections require explicit authorization and bounds of at
most 30 minutes; continuous product operation is a separate configuration.

**Device mechanism.** Extend the device ARM/iiOD capture owner with a separately
negotiated ordered, continuous session. Keep one counter lease, one prepared
table of eight attested Fast Lock profiles, and the existing persistent DMA
capture stream for the lifetime of the run. Maintain a cursor `0..7`, a 64-bit
visit sequence, a 64-bit sweep sequence, and one active window. The cursor
advances only after the admitted window has been accounted for; an integrity
failure stops the run with the actual partial payload and an explicit reason.
ACTIVE, QUIET, and diagnostic UNKNOWN outcomes cannot alter the cursor.

For each target, reserve capacity before recall, obtain the recall's sample
counter bracket and profile CRC, establish the provider's attested valid start,
and clip the persistent DMA blocks to `[valid_start, valid_start + 50000)`.
Copy the exact samples before releasing their leases. Boundaries can cross DMA
blocks; excess tails are outside the visit and must not be padded into it or
assigned to the next tuning. Retain the full source counter and generation
across sweep and recording rotations. A counter discontinuity starts a new
explicit generation or terminates the run according to the declared source
policy; software delivery ordinals never become hardware counters.

Provider version defines late-recall handling. The older `libiio-feature-103`
reference uses `selection_counter + transition_budget_ticks` and rejects a
late completion; the `libiio-issue-119` reference moves a late valid start to
`recall.counter_after + transition_budget_ticks`. Neither inspection attests
the exact source of the installed `.15` binary. Consume the returned valid
start and persist its qualified boundary meaning, including whether the guard
is included. Do not add a receipt's guard twice. Begin with the measured 20 ms
allowance as an experimental profile; qualify smaller values using raw
transient/coded-waveform evidence and held-out repeats.

**2026-10-09 candidate correction.** The inspected device receipt pins kernel
`fastlock-attestation-v059-source/linux-v1` to
`d3611e575b09fa4e43be99a513423cb1ab3f4d37`. Its
`drivers/iio/adc/ad9361.c` reads `ADI_REG_GP_STATUS` (`0xB8`) before recall and
after RX PLL lock, LO readback, and profile CRC checks. Candidate device commit
`44efe08` corrects unpublished continuous v5 to
`valid_start = max(selection_counter, recall.counter_after) + guard_ticks`.
It preserves finite v1–v4 behavior and all previously persisted receipts.
Completing just before the old planned boundary therefore receives the entire
configured guard in the reported counter domain; exact IQ support remains
50,000 samples.

The guard is a **reported-counter minimum**, pending physical settling
qualification. HDL synchronizes the raw sample counter into the GPIO register;
this snapshot has CDC age. The actual paired factor-one packer simulation gives
`FIFO_IQ_tag = prepack_IQ_origin_tag + 1`; neither the GPIO path nor the kernel
receipt applies that offset. Same-sample comparison must normalize the IQ
origin explicitly. Adding one tick alone cannot establish a physical 20 ms
minimum because snapshot age also remains unqualified. A shorter prior guard
does not by itself prove corruption or clean settling; retain those recordings
as measured evidence and qualify transients independently.

The corrected RAM candidate's bounded
[101-window canary](../../reports/2026_10_09_continuous_scanner/postguard-sweep-timing.json)
retained exactly 50,000 samples per receiver and measured a 20 ms reported
post-recall guard on every window. Median/max recurring sweep intervals were
352.8660/354.4156 ms; median/max valid-start spacing was 44.1080/44.9164 ms.
First-eight complete coverage from the first valid sample was 328.2524 ms.
A separate five-second TX canary retained all 112 captured windows, with 28
receiver decisions ACTIVE on the tone target and 196 QUIET elsewhere; both
device and host settings were restored. The
[component verification](../../reports/2026_10_09_continuous_scanner/postguard-component-tests.txt)
passed 185 tests. These are bounded observations, not a physical settling or
indefinite-operation qualification; see the
[implementation evidence](continuous-scanner-implementation.md).

**Continuous control and bounded memory.** Add an explicit `until_stop` setup and
ordered policy, preserving old bounded/weighted semantics. Size a ledger ring
from outstanding capture/delivery/control receipts; retire slots only after
delivery and relevant acknowledgment. Absolute visit IDs do not wrap with ring
indexes. Disable adaptive feedback. Allocate state, compile profiles, and create
buffers at start; visit and sweep boundaries require none of those operations.

Provide start, status, and idempotent stop controls keyed by run ID and generation
on a control path that can interrupt a blocked data read. A stop acknowledgment
means the request is accepted; the terminal receipt separately means capture
admission ended, accepted data drained, radio restoration completed, and the
exclusive owner was released. Normal stop finishes the active valid window
when safe; a cancellation/transport fault that prevents this retains its actual
partial count. A second start fails while the owner is active. Repeated stop
returns the same terminal result. A reader disconnection, exhausted storage,
DMA loss, or queue overflow is an explicit fault stop, never successful
unreported loss. Independent operation after losing the IQ consumer would need
device-local recording and is outside this first delivery.

Planned sibling commands are `leo scan continuous-start`, `continuous-status`,
and `continuous-stop`; these names are proposals, not commands available today.
Start validates the immutable target table, serial, policy, and output reserve,
then returns a run ID after device activation while a supervised receiver/writer
continues consuming data. Status reports the current target/sweep, per-target
age, faults, writer state, and restoration state. Stop accepts that run ID and
waits separately for the terminal cleanup receipt. A device control connection
does not drive individual visits, and closing a status client does not stop a run.

Rotate recordings on the writer thread without restarting acquisition. Reuse
64-window chunks; initially seal a version-1 segment every 512 windows
(204.8 MB raw dual-RX IQ). Local segment sequences start at zero, while acquisition
metadata retains run ID, global visit/sweep sequence, table digest, and generation.
Sealing resets neither the sample clock nor tuning. A bounded run checkpoint
names the latest sealed segment and terminal state. Check disk reserve before
opening each segment; do not silently overwrite older evidence.

Add a distinct continuous configuration/control contract; the existing Python
duration/visit contract keeps its meaning. Deploy its reader before its writer.

## Method

Established on 2026-10-09 from repository contracts, the digest-bound local
qualification summary, public PPU codecs/campaign code, and read-only inspection
of the device reference policy/session/UAPI. The public reference and installed
binary have different provenance; the first deliverable resolves that mapping.

**Smallest implementation surface.** External references remain read-only here;
future changes belong in separately authorized worktrees. Checked
`libiio-feature-103` revision `5518228d9181b95de7b7f3e2fdfe1fee438fbbf0` has older
rate validation; resolve the installed v0.60 source/build mapping first.

| Owner and files | Concrete change |
| --- | --- |
| Device iiOD `spf-scan-policy.c/.h` | Add an explicitly selected ordered cursor policy; preserve weighted selection for old setup versions. Ordered mode ignores power outcomes. |
| Device iiOD `spf-scan-session.c/.h` | Add continuous lifetime, absolute sequence plus bounded ledger retirement, uninterrupted source ownership, and stop/drain/restore states. Existing `duration/dwell + 1` allocation and terminal comparisons need separate continuous paths. |
| Device iiOD `spf-scan-protocol.c/.h`, `ops.c`, `parser.y`, `lexer.l` | Add capability-negotiated setup/control/status/terminal messages and route stop through the existing session lock/cancellation owner. Assign unused wire version/feature values after the combined IQ/power capability inventory; reject unsupported endpoints explicitly. |
| PPU `adaptive_scan.py`, `adaptive_scan_client.py`, `adaptive_scan_campaign.py` | Add matching strict codecs and a persistent prepare/start/read/stop/restore lifecycle. Keep the bounded campaign API. Support eight profiles directly instead of the seven-profile convenience builder workaround. |
| PPU `adaptive_scan_radio.py` and device `spf-scan-radio.c/.h` | Reuse acquire/configure/recall/release and immutable profile receipts; add changes only where capability or profile-zero tests demonstrate a need. The inspected counter ioctl configuration contains no campaign-duration field. |
| This repository `src/leo/acquisition/short_window_ppu.py`, `src/leo/scanner/short_window_recording.py`, `src/leo/cli/short_window.py` | Consume actual ordered provider visits, validate the order/counters, compose start/status/stop and bounded segment rotation, and expose coverage/integrity/durability separately. |
| This repository short-window contracts/storage/readers and existing recordings API/UI | Add run checkpoints and continuous controls; retain version-1 IQ segment readers, fixed CI16 geometry, hashes, and offline analysis. |

Device reference files reside in `/home/mouse9911/gits/libiio-feature-103/iiod`;
PPU files in `/home/mouse9911/gits/pluto-plus-utils/src/pluto_plus`. Audit the
Linux scan-owner UAPI and AD9361 implementation before assuming a kernel or HDL
change. Slot zero worked in the smokes; the convenience builder's contrary
sentinel comment still requires version-specific coverage/restoration tests.

**Native on-device alternative.** Compare the iiOD patch with a small device
capture composition over
[`local_source_port`](../../native/adaptive/device/local/local_source_port.h)
and the existing bufferless preparation owner. Reuse prepare/activate/prime,
recall/clip/release, cancellation, and restoration, with the same ordered policy,
descriptor, and recording port. Select one production acquisition owner.
[`scanner.cpp`](../../native/adaptive/scanner/scanner.cpp) presently requires
detector bindings, 120/240/360 ms dwells, a 100 ms execution-admission allowance,
and a bounded application deadline. Its
[`leo_scan_policy_create_continuous`](../../native/adaptive/policy/spf-scan-policy.c)
helper retains a circular ledger but does not make that application run until
stop. Add a detector-free capture entry point; preserve the existing ABI/tests.

**Timing acceptance.** Measure every quantity in the source clock separately
from host delivery. For valid intervals `[s_i,e_i)`, define gap
`g_i = (s_(i+1) - e_i)/rate`, visit spacing
`d_i = (s_(i+1) - s_i)/rate`, and per-target revisit
`R_t = (s_next(t) - s_previous(t))/rate`. Initial complete coverage is
`C8 = (e_7 - s_0)/rate` for the ordered first eight windows. These are different
from start-to-start sweep period and command wall time.

| Uniform total gap assumption | Initial complete coverage C8 | Per-target revisit / sweep period | Dual-RX raw payload rate |
| ---: | ---: | ---: | ---: |
| 20 ms | 300 ms | 320 ms | 10 MB/s |
| 5 ms | 195 ms | 200 ms | 16 MB/s |
| 1 ms | 167 ms | 168 ms | 19.05 MB/s |
| 0 ms | 160 ms | 160 ms | 20 MB/s |

The measured 20.231 ms median gap suggests approximately 302 ms initial coverage
and 322 ms recurrence under strict order; this is an inference, not observed
ordered-scheduler performance. The proposed initial qualification target is
**25 ms maximum total gap**, giving **335 ms maximum C8** and **360 ms maximum
per-target revisit**, with a 20 ms transition profile. Report p50/p95/p99/max,
number of samples, and deadline misses for gaps, C8, and each target's revisit;
report recall brackets, discarded support, delivery latency, classification
latency, writer backlog, and segment-sealing cost separately. A failing bound
stays visible and does not relax validity or drop targets. The previous CLI
classification p99 was 2.748 ms and delivery-to-classification p99 3.173 ms;
the proposed 1 ms p99 emission target remains unmet.

**Deliveries and gates.** Implement these increments in order within this
workstream; the FPGA power workstream can proceed at the same time.

1. Freeze the shared visit descriptor and new control capability. It identifies
   run/session/generation, global visit/sweep, target/table/profile CRC, requested
   and actual IF, optional RF authority, receiver layout, rate, valid sample
   interval, qualified guard identity, gaps, power policy, and failure state.
   Gate: old codecs reject unsupported new values, new readers preserve old
   recordings, and an unqualified endpoint cannot claim ordered continuous mode.
2. Implement ordered selection and bounded continuous session state using fake
   radio/DMA providers. Simulate beyond 16,384 visits, multiple ledger and segment
   wraps, and the low 32-bit device counter rollover at about 28.6 minutes at
   2.5 MS/s. Recall brackets carry low words while DMA supplies full counters;
   extension across wrap must preserve 64-bit interval continuity or explicitly
   fail/start a new generation. Use fixtures near `2^32`, requiring no new RF.
   Gate: exact `0..7` repetition under ACTIVE/QUIET/UNKNOWN combinations, every
   intact sweep covers all eight exactly once, no per-visit allocation, constant
   resident memory after warm-up, and checked sequence/counter overflow.
3. Add start/status/stop, recorder rotation, and reader/UI support. Inject arbitrary
   block sizes, stale/repeated blocks, counter rollover/gaps, retune failure,
   slow reader/writer, ENOSPC, cancellation during every lifecycle phase, and
   restoration failure. Gate: no false complete window, no unreported loss,
   readable sealed segments during later acquisition, bounded queues/metadata,
   and a terminal result that distinguishes request acknowledgment from cleanup.
4. Qualify an explicitly authorized short ordered run at the 20 ms allowance on
   the intended transport. Reuse the existing tone/recorded-IQ evidence first;
   new raw transition/coded-waveform tests cover all 56 directed profile pairs
   and wraparound in individually bounded follow-ups. Gate: exact 50,000-sample
   windows, all eight slots, zero missing/corrupt/unreported visits, measured
   gap/coverage/revisit bounds, restored radio state, and writer stress at the
   admitted rate plus 25% headroom. Wider jumps and held-out transient tolerance
   are required before promoting the profile.
5. Optimize only measured costs: recall execution, unused tails, delivery block
   geometry, classification, and sealing. Validate 5 ms or smaller transition
   profiles independently; a short recall ioctl does not prove signal settling.
   Gate: the same validity/coverage tests and exact-IQ offline GLRT parity hold,
   with improved gap distributions under declared load. Reader-first deployment
   and a separately authorized canary follow the existing deployment runbook.

Hardware/QNAP/PostgreSQL requirements remain explicit markers; QNAP is read-only
and scientific goldens stay fixed. Offline GLRT processes quiet and active
complete windows, bound to counter support/hashes. Tracking requires qualified
RF/UTC mapping; faster coverage alone establishes no localization improvement.

**Integration handoff.** IQ and FPGA power share the table, counter/generation,
exclusive owner, descriptor, and wire-value inventory. They start as separate
modes. Later fan-out can compare FPGA power against the same saved IQ interval.
IQ delivery does not depend on HDL arithmetic: hand off source/build receipts,
bounded-state tests, timing qualification, readers/controls, and rollback together.

Revisit this brief when the device protocol/build mapping, sample-counter ABI,
recording publication port, or measured transition profile changes. The
[full qualification/deployment plan](short-window-scan-plan.md) remains the
release gate.

## Existing-pipeline handoff qualification (2026-10-10)

Fast GLRT now has an adapter to the deployed shared scanner `TrackingInput`
port. `leo scan analyze-fast --export-tracking-input` publishes its immutable
input beneath the selected local artifact root. It preserves every completed
fractional candidate, actual device counters, receiver/channel/edge, IQ identity,
and the recorded LNB reference hypothesis. Skipped fast-score windows have no
invented GLRT result. Payload offsets and elapsed device-counter time remain
separate; retunes never become continuous IQ.

The existing PPU acquisition adapter records UTC/monotonic clocks before START,
at first-window delivery, and at every subsequent delivery in the sealed visit
receipts. The first valid sample is bounded by START request and first delivery;
delivery is not treated as sample acquisition time. The deployed
`PersistentHopUtcTimingAuthorityV1.from_host_bracket` constructs its usual timing
authority. Captures without this evidence do not gain an invented UTC anchor.

`tools/fast_scan_standard_pipeline.py` is a development composition harness, not
a replacement tracking or positioning component. Its `glrt` command uses eight
existing queue workers in an explicitly isolated test database, then exports the
input. Its `standard` command runs in the selected deployed worker environment
and calls `ScannerTrackingService` with the input port. `--regional` also invokes
the existing Hard60/B7 CLI; only its input-store factory is substituted inside
that isolated process. Existing tracking/TLE/conditional-position/B7 algorithms,
stores, schemas, renderers, priors and work bounds are retained. The installed
workers and production capture catalogue are not modified by this harness.

Run the owned phase with `python -m tools.fast_scan_standard_pipeline glrt` and
explicit `--recording` and `--output` arguments. Run the deployed phase with that
worker's Python/PYTHONPATH, `tools/fast_scan_standard_pipeline.py standard`,
`--input <output>/tracking-input.json`, a separate `--output`, and `--regional`.
Inspect both standard and regional completion states; a resumable time slice is
not analysis completion. The regional pipeline retains its matched fitted-c and
zero-c arms. Report frequency fit separately from location error.

RF hypotheses remain hypotheses throughout this qualification. In particular,
using 10.6 GHz as a CH5–8 reference does not establish that the physical LNB was
in that band. Any resulting satellite/position candidates are conditional on
those inputs, not an independently established location or identity.
