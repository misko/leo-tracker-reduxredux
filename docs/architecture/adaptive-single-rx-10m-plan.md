# Adaptive single-RX 10 MS/s, 300-second scanner plan

Status: implementation in progress; deployment gates remain open, 2026-09-12.
This document does not change the running scanner.
Baseline release: `98207d6fc6eaeaab1ab870998c1519afe0a6b892`.

Radio selection update: the user selected `104000bac4950008230026001b440a003a`
at `192.168.1.17` (`radio_pluto_003a`). Both receiver paths are now available;
the fixed single-RX profile has been switched to this radio. The
[replacement-radio checkpoint](../../reports/2026_09_12_radio003a_scanner_switch/README.md)
records the passing short capture and native analysis, acquisition release,
cancellation fix, and two failed 23:00 scheduled attempts. Both failures lost a
131,072-sample block; a bounded CPU1 worker-affinity comparison also failed.
After a larger-refill comparison and AGC-restoration fix, the 65.02-second
recheck passed at 95.4172% duty with zero loss. Acquisition release `eefcb4f0`
completed the 23:20 slot with 262,144-sample blocks: 95.4264% duty, zero loss,
successful restoration, and 2,386 RX0 visits. Native analysis processed every
visit, and Chromium verified all three source-bound figures. API/UI release
`7f82cf42` removes the disabled radio-classifier panel for this fixed profile.
This selection supersedes earlier
`.20` references and the historical exclusion of this serial.

Implementation checkpoint: the [2.5M decimated-dwell engine report](../../reports/2026_09_12_adaptive_decimated_dwell/README.md)
records working integer DSP and passing arithmetic/pilot controls, but the best
measured FIR pipeline still misses the ARM service-time gate. The same checkpoint
records intermittent refill failures in the existing fixed scanner. Stage 1 and
baseline reliability remain open; no adaptive deployment has occurred.

Latest execution checkpoint: recursive, FP32 FIR and FFT filtering experiments
also fail the full-coverage ARM timing gate. The unchanged direct-FIR pipeline
on the host measures 19.28 ms mean / 27.27 ms empirical p99 on sixteen development
dwells, excluding transport/feedback. A user preference is pending before changing
the on-radio architecture or six-window coverage requirement. The
[host-feedback proposal](adaptive-single-rx-10m-host-feedback-proposal.md) makes
that alternative concrete without activating it. The startup provider fix has
passed the replacement radio's short check, but complete-scan continuity remains
unqualified. Consult the report and its RF ledger for the current evidence and remaining
qualification allowance. The sequence below remains the intended on-radio design
until an explicit architecture revision is accepted.

## Deployment path and current readiness

The release has one critical path. Baseline reliability and decision-engine
feasibility can be investigated independently; both must pass before live adaptive
qualification. Build the remaining integration against the selected, sealed DSP
configuration, then deploy one compatible bundle.

| Step | Current evidence | Required exit |
| --- | --- | --- |
| 1. Qualify metadata reliability | Provider `26310f8`, larger 262,144-sample refills and PPU's AGC-restoration fix passed a short recheck and the replacement radio's complete 23:20 capture, analysis and browser check. | Carry this exact baseline into adaptive qualification and verify continuity, duty and restoration under the added decision/feedback load. |
| 2. Select the 2.5M decision engine | Integer FIR, FP32 FIR, recursive and FFT candidates all fail complete-pipeline ARM timing. The host comparison passes microbenchmark timing; architecture preference is pending. Held-out quality remains unqualified. | Combined mean ≤90 ms and p99 ≤100 ms, held-out fidelity and boundary checks, then 300-second paced replay with no growing queue, overload skips or expired decisions. |
| 3. Integrate capture through publication | Fixed single-RX 10M recording and analysis provide reusable components; adaptive interfaces still contain legacy geometry/rate restrictions. | Versioned provider/contracts, correct RX0/RX1 column mapping, native-10M analysis, decision provenance, API and browser assets pass component and compatibility tests. |
| 4. Qualify on the radio | Short baseline checks and failed candidates are retained in the linked RF ledger and replacement-radio report. No shadow/adaptive canary has run. | Uniform shadow RX0/RX1 and adaptive RX0/RX1 pass the live gates below. Stop on the first failure. |
| 5. Switch and verify | Fixed profile is the rollback target. | Switch the complete compatible release between scans; the first scheduled adaptive scan, analysis and web publication pass, with rollback verified. |

Keep an explicit RF ledger: four 300-second canaries use 20 minutes, the first
scheduled qualification uses five minutes, and five minutes remain for a bounded
baseline canary or retry. Count partial failed attempts too; never exceed 30
minutes of new qualification collection. If baseline qualification consumes the
reserve, there is no retry allowance. Saved-IQ benchmarks consume no RF budget.

Before expanding integration, resolve the decision architecture using these
measurements and the user's pending preference. Freeze the selected topology and
reference protocol before opening the reserved holdout. Preserve full coverage
unless an explicit reduced-probe design is accepted. Do not infer deployment
readiness from an idle-radio or host microbenchmark, or from the earlier
native-2.5M scanner. Continue baseline diagnosis independently.

For release review, produce one evidence index linking the exact source and
binary hashes, DSP qualification, component tests, canary receipts, RF ledger,
UI asset checks and rollback configuration. Gate failures keep the fixed profile
selected; uniform fallback during a scan does not constitute adaptive acceptance.

Deployment direction: **record and analyze native 10 MS/s; make adaptive
decisions on a causally filtered 2.5 MS/s stream on the radio**. Reuse the
existing worker: screen all six 20 ms windows, then perform at most one ranked
confirmation. This supersedes the native-10M-first and progressive-5M proposals.

Three reviewable stages lead to one production switch:
**qualify the decision engine → integrate capture through publication → run
bounded canaries and deploy**. Resolve ARM capacity before broad integration.

## Evidence and remaining risk

The [earlier native 2.5M live scan](../../reports/2026_09_10_scanner_lnb_live_checkpoint.md)
achieved 94.5317% duty, screened all 2,364 visits and demonstrated adaptive
weighting and demotion. Confirmation-bearing jobs reached 89.22 ms p99 wall time
and 95.41 ms maximum under capture load. The [earlier ARM replay](../../reports/2026_09_09_scanner_threaded_arm_checkpoint.md)
measured 58.71 ms mean / 68.98 ms p99 worker wall time. Neither included the new
10-to-2.5M decimator or concurrent 10M recording.

The [5M progressive prototype](../../reports/2026_09_12_adaptive_arm_progressive/README.md)
failed on ARM: approximately 190 ms CPU for one probe and 1.14 seconds for six,
against visits arriving roughly every 126 ms. It must not be deployed.

The [desktop study](../../reports/2026_09_12_adaptive_decision_budget/README.md)
also found decision differences after narrowing to 2.5M. The remaining question
is whether an accurate, inexpensive decimator plus the existing 2.5M worker
fits the budget while recording 10M. The study's 257-tap filter is a numerical
reference, not a qualified fast implementation. Existing evidence does not
establish duty or detection performance for this combined design.

## Intended behavior

Add `adaptive-single-rx-random-10m-300s-v1` on the user-selected `.17`
radio. Select physical RX0 or RX1 once from the durable scan identity; record
and classify that receiver for the whole scan, including retries. Record native
10 MS/s CI16 with 10 MHz bandwidth for 300 seconds, with 120 ms valid visits
and the existing eight pilot-centred targets and 20-minute cadence. Feed only
the separate 2.5 MS/s decision copy through the on-radio classifier; preserve
complete native IQ for offline analysis.

Use the latest validated fixed-profile transport settings as the adaptive starting
point. The replacement radio's current candidate uses 32 kernel buffers,
262,144 samples per block, read-ahead 8, writer queue 64, and one thread per math
library. The earlier 131,072-sample block size failed full scans on this radio.
Larger blocks and their feedback latency still require adaptive qualification.
The fixed profile remains the rollback choice. Migration is outside this change.

Preserve the current adaptive policy:

- Three uniform warmup visits per target, resetting at every scan.
- One positive promotes immediately; active:quiet visit weight is 3:1.
- Demotion requires three consecutive successfully evaluated misses and two
  seconds since the last positive source dwell ended. Unknown breaks the streak.
- All eight targets retain exploration; the planned revisit limit is three seconds.
- Results are source-bound, applied in source order, and expire after one second.
- Three unhealthy/missing/expired results, or an explicit feedback fault, latch
  uniform scanning for the remainder of that scan. Record the fallback reason.

Preserve the existing distinction between healthy intentional skips and
unhealthy feedback. Both remain UNKNOWN rather than an evaluated miss; test
their separate effects on the health latch. Healthy qualification must not
depend on skipping decisions to sustain capture.

These are scheduling observations, not proof of signal absence or satellite
identity. Actual revisit lateness must remain visible.

## Findings that determine the implementation

The fixed 10 MS/s profile deliberately disables the on-radio GLRT worker.
Adaptive capture currently requires that worker's `positive-only-v1` feedback.
Consequently this is more than a profile configuration change:

- Leo's `AdaptiveHopPlanV1` embeds the legacy dual-RX geometry and fixes
  `classification_receiver=1`. The native policy and SDK also reject RX0 and 10 MS/s.
- PPU `AdaptiveHopRequestV2` and libiio's adaptive admission only accept
  2.5/5 MS/s. PPU's adaptive stream assumes eight IQ bytes per time sample.
- Leo's adaptive mapper, writer and reader assume two payload columns/eight
  bytes per time sample. A one-RX stream requires four bytes and an explicit
  physical-RX-to-payload-column mapping.
- Adaptive analysis configuration and its CI16 reader enforce dual RX and
  2.5/5 MS/s. Fixed native-10M numerical primitives can be reused, but adaptive
  products must retain actual visit times and target order.
- Dispatch currently falls through to fixed hopping when an adaptive rate is
  outside the configured allowlist. The new profile must reject unsupported
  admission rather than silently run fixed while labelled adaptive.
- Shared refinement already handles recorded receiver IDs and native 10 MS/s;
  it needs the new adaptive reader. Shared tracking needs its adaptive input
  binding updated. Neither needs a second scientific implementation.

## Implementation sequence

### 1. Qualify the complete 2.5M decision engine first

Define the new intent with profile ID, policy/mode, selected receiver, rate,
bandwidth, detector configuration digest and durable operation identity. Include
shadow versus adaptive mode in the binding to prevent cross-mode retry collisions.
Keep physical receiver selection stable within a scan and across retries.

Use saved RX0/RX1 10M captures for development and reserve independent holdout
visits before inspecting their decisions. Include both pilot edges, all targets
and temporal windows, weak candidates, CFO extremes, negative-heavy stretches
and structured interference. Keep detector thresholds and six-window ranking
unchanged. Compare optimized filtering against the high-quality factor-four
reference using the same 2.5M worker. Separately report disagreement with native
10M offline evidence; neither reference is labelled RF truth.

Measure a multistage factor-two/factor-two decimator and a short polyphase
factor-four candidate. Freeze passband, stopband, alias rejection, precision,
quantization and boundary requirements before holdout evaluation. Preserve the
required pilot/CFO coverage. Select one implementation from measured fidelity
and cost, sealing coefficients, templates, thresholds and algorithm hashes.

Make sample-time conversion explicit: persist both rates, decimation phase,
filter identity, source interval and valid boundaries. For a linear-phase FIR,
the delay-corrected coordinate of decision sample `k` is native offset
`4*k + phase - delay` under the declared convention. A recursive filter has
frequency-dependent phase: retain its actual input-clock coordinate and phase
response rather than claiming one constant corrected delay. Qualify settling
and detector timing bias explicitly. Reset history at each hop; never use future
or previous-target samples. Mask unsupported initial samples and account for
final support. Validate all six windows; insufficient support yields UNKNOWN
rather than invented full coverage from padding. Amend and seal a topology-
appropriate arithmetic reference before holdout evaluation if the recursive
candidate is selected; the existing Q15 FIR reference alone does not cover it.

Benchmark the exact ARM pipeline, including filtering, extraction/copies,
screening, confirmation and IPC. Begin with bounded saved-data microbenchmarks,
then run a paced 300-second replay with modeled capture/transport load. Include
confirmation-heavy and negative-heavy arrivals. Modeled load prepares for live
shadow qualification; it does not establish RF coexistence.

Proposed engineering gates, frozen before qualification:

- Combined decision service time: mean at most 90 ms, p99 at most 100 ms at the
  approximately 126 ms arrival interval. Aim for filtering at most 10 ms p99:
  the earlier live detector already consumed much of this budget. These are
  targets, not measured performance; combined pipeline timing is authoritative.
- A paced 300-second replay has no growing queue, overload skips or expired
  results. Every accepted observation is younger than one second. Report CPU,
  wall time, maxima, feedback-age distributions, memory and queue occupancy.
- Every healthy visit has complete screening accounting; confirmation remains
  conditional on the screen. Partial evaluation is UNKNOWN. A budget checked
  after a nonpreemptible probe is a soft limit, not a throughput guarantee.
- ARM filtering matches the frozen scalar reference within an explicitly tested
  quantization tolerance, with no unexplained optimized-versus-reference
  decision changes on holdout. Explain threshold-boundary differences separately.
  Controls cover aliases, noise, tones, clipping, phase, CFO and every temporal
  window. Report candidate retention/disagreement by RX and target; do not tune
  thresholds to remove holdout failures or change golden fixtures.

Exit artifact: sealed decision configuration, component-owned tests, selection
manifest and ARM timing/quality report. If the gate fails, revise this stage
while the fixed profile stays selected. Fewer probes require a separate coverage
and miss-semantics design; they are not a silent fallback for this release.

### 2. Extend the existing provider and SDK through explicit versions

Add a versioned single-RX adaptive request/capability in PPU and libiio, leaving
published V2 requests unchanged. Extend the native scheduler/GLRT entrypoints
with explicit selected-RX configuration while preserving legacy entrypoints.
Carry that receiver through worker jobs, sample extraction, observations and
result validation; reject feedback from the other physical receiver. Carry both
rates, native source interval, filter identity and coverage through the versioned
decision binding. Keep 10M IQ out of the old classifier: removing rate checks is
unsafe because its pilot scratch arrays also assume lower rates.

Keep the existing acquisition-owner thread, bounded feedback queue and native
counter-based scheduler. At 10 MS/s a valid visit is 1,200,000 samples, the
cooldown is 20,000,000 samples, and the nominal scan spans 3,000,000,000 samples.
Audit integer widths, counter wrap, source epochs and deadline conversions.
Measure classifier load concurrently with transport. Missing or late processing
must produce explicit UNKNOWN/fallback accounting while capture remains bounded.

### 3. Add adaptive contracts and complete single-RX recording

Add new versions for adaptive plan/receipt, capture manifest, timing authority
and dependent bindings where their public schema changes; preserve existing
dual-RX readers and artifacts. Reuse the fixed single-RX geometry rather than
duplicate rate, target or RX-selection rules.

Update PPU stream reconstruction, Leo mapping, queued writing and reading to
derive payload width from recorded receiver IDs. Physical RX1 still occupies
payload column zero when it is the only receiver. Retain every valid sample,
actual transition, target choice, decision basis, terminal tail and restoration
receipt. Storage chunks may group eight visits; they must not imply a sweep.

Wire the new profile into scheduled dispatch, admission, restart, durable queue
retry and deployment capability checks. A detector fault during a scan uses the
existing recorded uniform fallback; missing capabilities at startup reject the
profile before collection. Neither changes the selected receiver.

### 4. Extend native-rate analysis and the existing web views

Version the adaptive analysis configuration/products for 10 MS/s and one RX.
Reuse the native 10M GLRT/CFO implementation, with time/frequency axes derived
from recorded counters and sample rate. Analyze actual visits independently of
target order; never infer missing visits, a second receiver or equal sweeps.

Start with the deployed production density: one 20 ms probe per 120 ms visit,
two bounded analysis workers, and resumable checkpoints. Keep complete IQ for
denser reanalysis and display the sampling density. Require analysis and normal
publication to fit the 20-minute cadence without a growing backlog.

Extend adaptive history/detail APIs with versioned schemas and update the
existing adaptive UI: selected RX, recording 10 MS/s / decisions 2.5 MS/s,
duty, decision coverage, allocation, actual revisit
gaps, decision freshness and fallback reason. Generate coverage, GLRT/CFO,
refinement and trajectory/TLE diagnostic assets through the existing publishers.
Keep live scheduling evidence distinct from offline candidate evidence. Existing
TLE propagation failures remain explicit and do not become invented matches.

### 5. Verify from saved data, then shadow, then adaptive

Every changed component owns tests. Cover both physical receivers; legacy
contracts; wire negotiation; exact byte/sample accounting; cancellation and
restoration; counter wrap; stale, duplicate, reordered and wrong-RX feedback;
checkpoint resume; and API/PNG manifest binding. Exercise all 256 target masks,
warmup, promotion/demotion, unknowns, exploration and latched fallback at 10M.

Use the existing 300-second captures for numerical replay and paced integration
tests. Replay can verify decisions for observed dwells; it cannot establish what
RF would have existed at hypothetical adaptive visits. Do not claim sensitivity
or allocation benefit from such counterfactual data.

Within the user's authorized bounded deployment qualification, use four
300-second canaries:
shadow RX0, shadow RX1, adaptive RX0, adaptive RX1. Shadow keeps uniform actual
hops and records proposed decisions. Receiver forcing is an explicit canary
override, never the production random policy. Nominal RF budget is 20 minutes;
cap all collection, retries and the first scheduled qualification scan at
30 minutes. Reserve five minutes of that budget for scheduled verification.
Do not overlap the existing scanner on the radio. Stop on qualification failure.

Proposed acceptance criteria, frozen before live testing:

- Zero missing samples, overflows, lost hop events or receiver-binding errors;
  full nominal duration and verified radio restoration.
- At least 95% usable duty and no more than 0.5 percentage-point regression
  against a representative fixed baseline. The measured fixed 95.49–95.51%
  is a reference, not a promise for adaptive capture. Duty is retained valid
  sample time divided by the attested source-counter span, including transitions;
  it is separate from decision coverage and the 20-minute schedule.
- No overload skips, expired decisions, sustained feedback backlog or unexplained
  fallback in healthy qualification runs; every accepted result satisfies the
  one-second age bound. Injected faults demonstrably trigger uniform fallback.
- Policy decisions match the independent model. Revisit deadline misses are
  measured and explained; no starvation hidden by aggregate duty.
- Native-rate analyses and all applicable UI artifacts complete within the
  cadence budget. Browser images decode, sealed hashes match, physical RX labels
  are correct, and old scans remain viewable.

### 6. Deploy as one profile switch with a tested rollback

Pin the compatible Leo/PPU/libiio/worker/template/filter bundle and run normal
release qualification. Retain current selectors, environment and release bundle;
verify rollback admission before switching. Switch acquisition and dependent
analysis/API selectors together between scans after canaries pass; preserve
radio, transport settings and cadence. Verify the first scheduled adaptive
capture through analysis and browser publication within the RF budget, then
leave the normal schedule active after acceptance.

If a live gate fails, stop additional adaptive starts, restore the prior complete
release/configuration and select `single-rx-random-10m-300s-v1`. Check radio
restoration and service health; retain all adaptive artifacts and failure
evidence. Within-scan uniform fallback protects capture but does not qualify as
successful adaptive deployment. No corpus migration, new processing service or
firmware flash is planned.

## Review checkpoints

1. **Decision engine:** efficient 10-to-2.5M filtering plus existing worker passes
   ARM and holdout gates; freeze the configuration.
2. **End-to-end integration:** versioned provider, storage, native analysis and
   browser publication pass saved-data and compatibility qualification.
3. **Release:** bounded shadow/adaptive canaries pass; switch the scheduled
   profile, verify publication and retain a verified rollback path.

These are dependency checkpoints, not three mandatory deployments. Done means
the scheduled random-RX adaptive profile completes capture, native-10M analysis
and browser publication while meeting the gates above. The immediate next task
is the efficient decimator paired with the existing 2.5M worker on saved IQ.
