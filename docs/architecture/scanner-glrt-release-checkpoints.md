# RX1 scanner GLRT: implementation and release checkpoints

Planning review: 2026-09-08. This is a focused execution plan, not a claim that
the feature is deployed or qualified. It consolidates the remaining work from
the [implementation plan](arm-single-rx-presence-plan.md); the historical
checkpoints linked there remain evidence, not interchangeable release passes.

## Outcome and invariants

For each counter-attested 120 ms scanner dwell, evaluate RX1 on the radio ARM
and return attributable evidence through the existing libiio capture session.
Keep dual-RX IQ recording, 300 s capture duration, eight-edge hop order,
sample-rate schedule, bandwidth/IF, guards, and recording duty unchanged.

The production design is asynchronous:

1. The existing acquisition owner forwards dual-RX IQ without waiting for GLRT.
2. A bounded collector copies RX1 valid samples into preallocated worker storage.
3. An isolated native worker screens the whole dwell and performs bounded
   fractional GLRT confirmation. It owns no radio-control or IIO handles.
4. Later IQ frames carry completed results referring to their original dwell.
5. After capture ends, a negotiated metadata-only drain delivers the tail before
   the owning session closes. This requires no extra IQ acquisition.
6. The host validates source geometry and publishes independent detector
   evidence; classification failure cannot suppress recording or re-analysis.

This requires an opt-in ARM userspace worker and iiOD/libiio/host changes, not
an FPGA change, kernel change, or firmware flash. It is a custom negotiated
extension, not a capability assumed to exist in stock libiio. No second receive
buffer, per-dwell process launch, Python-on-ARM dependency, or result service is
needed. No production restart, deployment, merge, or RF is authorized by this
planning document.

## Verified starting point

| Area | Existing evidence | Still open |
| --- | --- | --- |
| Native worker | Full 120 ms RX1 screen plus fractional confirmation; paired desktop/ARM replay | Independent detection quality, startup tail, 5 MS/s headroom |
| ARM scheduling | Two 300 s repeated-dwell runs; 2,381/2,381 results at each rate | Original block and metadata arrival, concurrent capture load |
| Provider/transport | Opt-in provider, envelopes and terminal drain; combined real provider/network/host passes short faults and both full 300 s accelerated counter spans | Original-arrival replay and representative capture contention |
| Host | Concrete backend/session and source-attested result accounting; 317 Leo / 182 PPU regressions plus 16 combined network tests | Release packaging and live qualification |
| Runtime/publication/UI | Explicit default-off opt-in; independent source-bound publication and scanner panel; 167 portable Python / 104 web tests | Production browser/database E2E, packaging/deployment and live qualification |

The [worker receipt](../../reports/2026_09_08_arm_presence_dwell_worker_checkpoint.md)
measures p99 CPU of 64.54/113.47 ms at 2.5/5 MS/s. At 5 MS/s, copy-to-result
p99 is 126.62 ms; an earlier cold execution also skipped work. The 100 ms CPU
target is not passed. The [quality checkpoint](../../reports/2026_09_08_arm_presence_screen_quality_checkpoint.md)
records 30/35 development reference-positive dwell flags, only 22/35 matching
reference timing/CFO, and 5/80 negative-control false flags. These are not
independent operational sensitivity/specificity estimates. The
[provider checkpoint](../../reports/2026_09_08_scanner_glrt_provider_checkpoint.md)
establishes offline integration, not unchanged live duty.

## C0 — Freeze the baseline and acceptance criteria

Work:

- Fetch remote revisions and inventory the existing implementation branches and
  unfinished host changes. Reconcile in isolated worktrees; do not overwrite or
  silently rebase unrelated work. Record exact source and artifact identities.
- Freeze rate, RX1, channel/edge, fractional timing, whole-dwell coverage, and
  valid counter geometry. Separate development scans from a fresh holdout by
  scan/session, not adjacent windows.
- Declare detection operating targets and the intended SNR/interference range
  before opening holdout results. Positive detection and an absence claim have
  separate gates. Unlabelled RF is unresolved, not a negative control.
- Freeze baseline device-counter duty, invalid-hop distributions, IQ continuity,
  CPU/wall latency, memory, result latency, and coverage measurements.

Tests/gate: reproduce the current detector outputs and known false flags;
verify input hashes, transition exclusion, and default-off capture regressions.
Deliver a versioned experiment manifest and acceptance checklist.

## C1 — Qualify detector quality and reduce ARM tails

These are independent work streams; both must pass. Neither transport success
nor matching the desktop implementation qualifies signal classification.

Quality work/tests:

- Compare the cheap six-slice screen plus bounded fractional confirmation to
  dense fractional reference analysis of complete saved dwells.
- Test weak and strong injections throughout all six slices, bursts crossing
  slice boundaries, fractional delay, CFO sweep/grid edges, Doppler variation,
  clipping, noise, stationary/two/pulsed tones, and wrong-pilot controls.
- Separate numerical parity, reference-associated detections, false alarms,
  missed detections, and unresolved RF. Report rate/edge/SNR breakdowns and
  uncertainty reflecting dependence within scans.
- Tune only on development data, freeze the policy, then evaluate fresh holdout.
  Do not enable the post-hoc threshold that rejects already-known failures
  without qualification. Searching all slices is not itself proof of absence.

Runtime work/tests:

- Profile collector copies, screen, confirmation, result conversion, and IPC.
  First optimize exact work reuse, allocation/planning outside capture, memory
  traversal, and measured hotspots; keep altered searches separately named.
- Compare identical inputs and settings on desktop and an approved idle ARM
  target using archived IQ only. Measure cold and warm CPU/wall p50/p95/p99/max,
  end-to-end age, memory high water, and startup readiness separately.
- Target total detector CPU p99 <=100 ms per dwell at both rates. The previous
  5 MS/s p99 needs at least 13.47 ms reduction to meet that target; this is not
  a prediction of attainable speedup. Include input handling consistently.
- Require bounded backlog and zero skipped valid dwells in normal replay, not
  merely a fast average. Initialize and exercise workspaces before acquisition;
  validate that startup preparation actually resolves the observed cold tail.

Gate: qualified decision policy and measured runtime headroom. If only every-Nth
dwell fits, label it a reduced-coverage experiment; do not silently substitute
it for the every-dwell goal. A sampled negative is not a whole-dwell absence.

## C2 — Finish the production host integration

Work:

- Add the optional metadata-extension port without detector dependencies in the
  generic capture component. Negotiate capabilities and algorithm/configuration
  identities before buffer creation; unsupported peers retain legacy capture.
- Unwrap and validate existing metadata as before. Register independently
  attested hop geometry before matching detector results to source dwells.
- Preserve uint64 source epochs and separate fractional offsets. Carry session,
  generation, sequence, RX, rate, channel/edge, counter bounds, searched coverage,
  scores, algorithm identity, timing, verdict, and reason.
- Distinguish pending, complete-qualified, complete-unqualified, failed, skipped,
  and incomplete states. Missing work must never become no-signal.
- Drain only after terminal capture validation and before close; bound retries
  and individual RPC timeouts. Reconcile the final expected dwell inventory.
- Publish a separate versioned evidence product through a narrow sink. Do not
  mutate published recording/analysis receipts or put storage work in refill.

Tests/gate: old/new client-server combinations; default-off byte compatibility;
late/duplicate/stale/wrong-dwell records; counters above 2^53; unsupported or
mismatched capabilities; malformed envelopes; cancellation; worker failure;
final result after last IQ; timeout or missing FINAL; complete inventory checks.
Recoverable detector faults preserve IQ; unrecoverable framing errors remain
real capture errors. Tests must distinguish those cases.

## C3 — Prove the combined provider-to-host path offline

Work: connect the actual provider, real network transport and production host
adapter in one hardware-free fixture, then replay archived original block,
counter, and hop-event arrival sequences for 300 s at each rate. Do not replace
the latter with a repeated pack delivered as evenly spaced whole dwells.

Tests/gate:

- Compare enabled/disabled IQ and inner legacy metadata byte-for-byte on identical
  replay input. All valid dwells must be accounted for, including the final one.
- Exercise arbitrary block splits, delayed hop metadata, gaps, partial dwells,
  cancellation, stale sessions, queue saturation, worker death, and disconnects.
- Require bounded memory, no acquisition waits for detector completion, zero
  normal-mode skips/losses, and no growing queue. Under deliberate overload,
  detector work may become explicitly unavailable; IQ delivery must remain intact.
- Run component regressions, C/Python wire parity, sanitizers, and ARM cross-builds.
  Record which portions execute on ARM rather than merely cross-compile.

## C4 — Verify evidence publication and operator visibility

Work: expose per-dwell detector status independently of normal scanner analysis,
with source visit, score, coverage, result age, and an explanation for unavailable
evidence. Preserve raw recording and the existing dense analysis workflow.

Tests/gate: delayed updates land on the correct visit; missing/failed results
render unknown rather than negative; publication survives detector failure;
reloading reproduces the same evidence; old scans remain viewable. No confidence
percentage or calibrated Starlink label is inferred from a raw GLRT score.

## C5 — Authorized live same-duty verification

Prerequisites: software gates passed, reviewed real artifact hashes, rollback
prepared, and explicit authorization for new RF. Use only an identity-attested
idle spare over 192.168.1.*, never serial 104000bac4950008230026001b440a003a.

Start with a bounded smoke check, then matched disabled/enabled 300 s runs at
each rate. Four runs require 20 minutes of RF; keep the total authorized campaign
including smoke <=30 minutes. Do not displace production recording. Rotate run
order to reduce order effects. More replication needs a separate bounded plan.

Measure retained valid sample time divided by device-counter capture span,
not 300 s nominal duration or host publication time. Record hop timing tails,
CPU/IRQ/network contention, missing samples, overflows, restoration, detector
coverage, backlog, and source-result alignment. Report setup and final drain
separately from RF duty and from result-latency distributions.

Gate: no observed duty reduction against matched baseline, no IQ loss/overflow,
no delayed hopping attributable to GLRT, valid restoration, and qualified
every-dwell evidence. Report uncertainty; a short A/B test cannot prove an
exact zero performance effect. Inconclusive evidence is not a pass. Do not
silently allow a positive duty-regression tolerance or change dwell/guard timing.

## C6 — Review, merge, opt-in deploy, verify

Package exact compatible SDK/worker/template/libiio/host revisions; verify actual
files against the approved manifest, not configured digest strings alone. Review
and merge in dependency order only with authorization, then pin released commits.
Deploy behind an explicit feature flag with a tested rollback to existing capture.

Tests/gate: installation preflight, identity negotiation, legacy fallback,
rollback, result persistence, and authorized canary verification pass. Promote
only after reviewing quality, timing, coverage, and duty receipts together.

## Delivery discipline

Each checkpoint produces a small receipt: source/input hashes, commands, test
counts, measured distributions, failures, limitations, and a pass/fail decision.
Keep numerical optimization, wire integration, host binding, and presentation
changes independently reviewable. Reuse the existing implementation; do not
restart completed checkpoints or claim their narrower results prove release.

The [host checkpoint](../../reports/2026_09_08_scanner_glrt_host_checkpoint.md)
now completes and tests the opt-in host adapter and exposes immutable evidence.
The [combined network checkpoint](../../reports/2026_09_08_scanner_glrt_network_checkpoint.md)
now closes the actual provider/network/concrete-host fixture gap, including
full 300 s accelerated synthetic counter spans and short fault cases. It does
not complete C3's original-arrival or load qualification. The
[runtime checkpoint](../../reports/2026_09_08_scanner_glrt_runtime_checkpoint.md)
now implements explicit runtime opt-in and independent post-capture publication,
API and UI, with fault-isolation tests. It is not a live partial-product UI or
a qualified/deployed classifier. Immediate next: original block/event arrival
replay, measured ARM headroom and held-out quality; release-local userspace
packaging and full production E2E also remain open.
The main scientific and performance release risks remain classifier specificity
and the 5 MS/s CPU/startup tail. No new RF is needed to work on either risk.
