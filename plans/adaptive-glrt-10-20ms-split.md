# Future adaptive scans: balanced 10/20 ms GLRT stride trial

Prepared 2026-09-29. Planning only: no acquisition, processing jobs, service
changes or production deployment have been performed for this plan.

Follow-up [deployed pipeline audit](../reports/2026_09_29_adaptive_glrt_audit/README.md)
confirms the full-scan 120 ms stride using running commands and saved products.
It also identifies an automatic **20 ms stride replay on up to 64 selected
dwells** inside relative phase. Carry the parent assignment consistently, but
preserve this explicit derived replay at 20 ms in both experiment arms. The
main-probe capacity figures below exclude this replay and downstream processing.

## Objective and baseline

Keep 20 ms GLRT windows and assign half of future eligible adaptive recordings
to 10 ms stride and half to 20 ms stride. Both receivers and all visits of a
recording share its assignment. Preserve the normal analysis chain and publish
every artifact required by each stage's contract through the web UI.

This changes temporal sampling density, not RF bandwidth, GLRT integration
length, or frequency-search resolution. For valid dwell length D, probe count
per receiver is floor((D - 20) / stride) + 1:

| Valid dwell | 10 ms stride | 20 ms stride | Existing automatic 120 ms stride |
|---|---:|---:|---:|
| 120 ms | 11 | 6 | 1 |
| 240 ms | 23 | 12 | 2 |
| 360 ms | 35 | 18 | 3 |

The proposed mix uses about 76–77% of the probes of an all-10-ms workload,
but roughly 8.5–8.8 times the probes of today's automatic 120-ms workload.
These are work-count estimates, not promised wall-time multipliers. Measure
CPU, memory, rendering, storage and queue drain capacity before activation.

**Baseline decision:** this plan assumes the user's literal 10/20 ms request.
The live production queue currently schedules 120 ms stride, not 10 ms. This
difference has been raised with the user; if the intended goal is instead half
the work of current production, revise the experiment before implementation.

## Findings that determine the design

Read-only inspection of the deployed worker source and matching source files
under `/home/mouse9911/gits/leo-adaptive-png-no-legends` found:

- `src/leo/cli/adaptive_hop_analysis.py` already accepts strides
  10, 20, 40, 60 and 120 ms. Existing analysis bindings distinguish configurations.
- `src/leo/cli/adaptive_processing_queue.py` hard-codes 120 ms in enqueue,
  subprocess arguments, completion checks and tracking handoff. Completion
  includes relative phase and downstream positioning, not just GLRT metrics.
- `src/leo/storage/scanner_tracking_source.py` constructs the adaptive metrics
  binding using 120 ms. Merely changing the analysis CLI leaves tracking reading
  the wrong product or reporting missing metrics.
- `web/src/adaptive-analysis-api.ts` permits only 10 or 120 in its stride type.
  `AdaptiveAnalysisPanel.tsx` defaults to 120 and describes 10 as manual-only.
- `AdaptiveRelativePhase.tsx` sends status and PNG requests without a stride,
  despite the server supporting configuration-specific relative-phase access.
- `adaptive_relative_phase.py` explicitly changes stride to 20 ms for selected
  dwell re-analysis. Distinguish this local replay from its main-analysis parent
  binding; it does not publish an all-visit 20 ms metrics product.
- Queue, worker and API use separately pinned releases. Reconcile their effective
  versions and preserve later production fixes before choosing the implementation
  base. This chat's checkout lacks much of the deployed adaptive implementation.

Source landmarks are observations, not instructions to edit installed releases.
Implement in a suitable isolated checkout of the production lineage, preserving
unrelated work; deliver a reviewable change before deployment.

## Implementation sequence

### 1. Freeze one assignment per recording

Use the existing PostgreSQL catalogue and local artifact stores. Add a small
versioned analysis-assignment contract, exposed through a narrow port, binding:
session ID, raw manifest digest, policy revision, activation boundary, arm,
20 ms probe length, resolved stride and configuration digest.

At first publication/enqueue after an explicit capture-time activation boundary,
assign recordings in balanced pairs within radio/sample-rate strata. Each pair
contains one 10 ms and one 20 ms recording; deterministically randomize pair
order using a frozen seed. Allocate pair positions transactionally, with a unique
session/raw-digest assignment. This avoids coupling the arm to a rate-selection
cycle and gives exact balance for completed pairs; an unfinished pair can differ
by one. Report both global and per-stratum balance rather than claiming every
odd-sized prefix is exactly 50/50.

Persist allocation before analysis results exist. Retries, concurrent enqueuers,
late publication, restarts and failures must not change an assigned arm. Record
assignment order explicitly; do not recompute it from a mutable history listing.
Retain failed sessions in the experiment denominator. Eligibility is defined by
capture metadata, not signal strength or analysis success.

Before activation, leave historical sessions and queued jobs on their existing
configuration. Re-analysis of old IQ for testing is explicitly scoped and uses
separate output roots. Never rewrite published capture or dataset contracts.

### 2. Carry the binding through the entire pipeline

Resolve the saved assignment once and pass the exact configuration/metrics
reference through queue lease, GLRT, rendering, relative phase, tracking and
position methods. Workers must not infer stride from whichever product exists.
The phase stage must retain an explicit derived 20 ms replay configuration in
both arms, with provenance distinguishing it from the parent assignment.

Include the assignment/configuration digest in idempotency and job identity.
Replace session-only "already queued/complete" shortcuts with checks against
the selected raw and analysis bindings. An old complete 120 ms product cannot
satisfy a new 10 or 20 ms job. A tracking/position result from a different metrics
digest cannot satisfy the selected job either.

Use existing configuration-addressed metrics stores. Where a downstream store
only supports one result per session, introduce a compatible versioned output
contract or explicit selected-product reference instead of silently overwriting
another configuration. Keep historical readers and URLs valid. No opportunistic
fallback to another stride when the selected product is partial or absent.

Do not retune detection, association, support or scoring thresholds in this
change. Verify all time calculations use actual probe timestamps. Preserve
deferred groups and scientifically valid insufficient-signal outcomes.

### 3. Make the UI follow the selected configuration

Expose the persisted assignment through a versioned public API. New scan pages
default to their assigned analysis; old pages resolve to their historical
configuration. Keep explicit viewing of other published configurations possible.
Show "20 ms windows / 10 ms stride" or "20 ms windows / 20 ms stride".

Pass the selected stride and binding to status requests, phase requests and PNG
URLs. All downstream panels must use the same selected metrics authority. Include
configuration/artifact digests in cache keys; clear state and cancel stale
requests when switching session or configuration. UI selection must not enqueue
analysis. Correct the existing descriptions of automatic/manual scheduling and
variable-length dwells.

### 4. Define complete publication from artifact contracts

Generate a per-session acceptance inventory from the selected stage contracts
and manifests, and verify required names against the contracts. Enumerating only
whatever files happen to exist would miss omitted figures.

| Stage | Publication checks |
|---|---|
| GLRT overview | `coverage`, `glrt64-response`, `cfo-trajectories` |
| Relative phase | `relative-phase-overview`, `relative-phase-dwells`; preserve the contract's diagnostic figures for insufficient/not-applicable outcomes |
| Dual-RX phase variants | `dual-rx-phase-progression`, `dual-rx-double-difference-time` when their declared state requires them; otherwise an explicit terminal reason |
| Tracking | `trajectory`, `trajectory-tle`, applicable `position-diagnostic`, and every declared `tle-review-*` |
| Position methods | `expanded-doppler`, `orbit-corrected`, `identity-mixture` according to their contracts |
| Blind regional | `blind-association`, `blind-position`, `blind-position-modes` according to their contracts |
| Adaptive TLE position | Contract-required `map` artifact for each enabled version |

Freeze the exact required/conditional matrix from the implementation before
testing. Do not make currently optional research products mandatory by accident,
and do not classify a missing mandatory PNG as "insufficient signal".

For every required figure: verify manifest digest and byte count, HTTP 200,
`image/png`, PNG signature and successful decoding with nonzero dimensions.
In a real browser, open both arms, scroll lazy images into view, check successful
image loads and open/download links, and retain network/error evidence. Wrong
configuration/digest requests must fail explicitly instead of serving another
arm's image. A render failure must leave publication incomplete and retryable.

## Tests and bounded validation

1. **Component tests:** exact probe schedules for 120/240/360 ms valid dwells;
   10/20/120 ms configurations; every supported rate and receiver layout;
   no probe crosses a retune or invalid span. Test distinct bindings and correct
   coverage accounting. Extend owned scanner/application/storage tests.
2. **Queue/catalogue tests:** pair balance within strata, frozen assignments,
   concurrent enqueue, deduplication, restart, lease expiry, retry/resume,
   late publication, activation boundary and historical jobs. Verify handoff
   after leaving the existing two-hour enqueue window. PostgreSQL integration
   uses its explicit marker and isolated test database.
3. **Full pipeline tests:** execute both configurations through phase, tracking
   and all standard position stages. Inject stale 120 ms results, missing PNGs,
   interrupted renders, partial metrics, wrong metrics digests and worker failure.
   Check recovery without duplicate work or cross-configuration reuse. Include
   no-detection/insufficient-support inputs and the legacy 120 ms path.
4. **API/UI tests:** extend adaptive analysis/phase/tracking/position API tests,
   `AdaptiveAnalysisPanel`, `AdaptiveRelativePhase`, `ScannerTrackingPanel` and
   downstream panel tests; add real browser coverage of both arms plus a historical
   scan. Test refresh and rapid session/configuration switching for stale PNGs.
5. **Saved-IQ comparison:** freeze a small, outcome-independent panel covering
   sample rates, dwell lengths and signal conditions. Analyze exactly the same
   excerpts at both strides in isolated roots, in checkpointed batches capped at
   10 minutes each. First measure cost on a small panel; do not expand into a
   multi-hour campaign. Match common windows by actual sample start, not probe
   index, since stride changes probe numbering. Compare scores/CFO/epoch within
   declared numerical tolerances; investigate any implementation divergence.
6. **End-to-end publication rehearsal:** first use complete small fixtures, then
   one saved production recording per arm with a predeclared compute cap after
   measuring projected cost. Traverse real queue -> worker -> API -> browser,
   retaining all stage receipts and the artifact acceptance inventory. A bounded
   attempt that cannot finish is a capacity finding, not a passing canary.

Scientific comparison reports detection coverage, track continuity, CFO residuals,
support/abstention rates, CPU/wall time, peak memory, output size and time until
all required PNGs are accessible. Keep denominators and failed cases. The 20 ms
arm is not expected to reproduce all detections from the overlapping 10 ms arm.
Do not treat overlapping probes as independent scientific samples. Publish paired
per-recording differences and predeclare acceptable scientific degradation before
using the live split to decide whether to adopt the lower-density arm.

## Release gates and rollback

Deploy only after all compatibility and artifact checks pass for both arms and
legacy 120 ms scans. At the current capture cadence, measured aggregate service
capacity must exceed incoming work with at least 20% headroom; evaluate queue-age
trend, downstream rendering and I/O as well as GLRT throughput. If the 10/20 mix
cannot sustain that load, leave the assignment policy disabled and report the
measured requirement; do not silently reduce density or raise worker counts.

Ship compatible readers/API/UI first with the policy disabled, then matching
workers and queue code. Verify the effective systemd release pins. Activate one
policy revision at an explicit boundary after the deployment is authorized.
Use the already-running capture stream; this plan authorizes no additional RF
collection. Observe an initial small balanced cohort through the final PNGs.

Stop assigning new experiment sessions if required artifacts are missing,
configuration bindings disagree, historical views regress, or queue capacity
fails. Disable new assignments and return unassigned future sessions to the
previous policy. Keep already-assigned jobs pinned to their original configuration;
pause them explicitly if necessary, preserving checkpoints and published results.
Do not reinterpret an existing 10/20 job as a 120 ms job during rollback.

Deliverables: implementation PR, frozen policy/activation record, component and
browser test receipts, paired saved-IQ report, complete artifact checklist for
each canary, capacity estimate and a verified rollback procedure.
