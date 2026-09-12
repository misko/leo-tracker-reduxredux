# Host decisions for the single-RX adaptive scanner — proposal

Status: proposed, pending the user's decision. The accepted deployment plan still
places decisions on the radio. This document does not activate a new profile or
reduce probe coverage.

The unchanged six-window pipeline exceeds the ARM timing gate on both radios.
The replacement `.17` radio replayed the same sixteen development cases with the
same compact-filter binary and inputs: 119.97 ms mean / 123.45 ms maximum wall
time, with bit-exact filtering. The earlier host direct-FIR comparison measured
19.28 ms mean / 27.27 ms empirical p99, excluding transport and feedback.
Neither benchmark qualifies a deployment or held-out detection fidelity.

## Proposed division of work

Keep capture and retune execution on the selected radio, with the existing
counter-authoritative policy engine. Record native 10 MS/s CI16 from one physical
RX chosen once per durable scan identity. Keep the 300-second duration, eight
targets, 120 ms valid visits and 20-minute cadence.

On the host, process a separate decision copy of each complete visit through the
sealed 10-to-2.5 MS/s filter, all six 20 ms screens, and at most one ranked blind
confirmation. Preserve thresholds, promotion, demotion, exploration and uniform
fallback semantics. The native recording and offline analysis retain 10 MS/s IQ.

Use a bounded worker queue with two waiting native visits as the initial measured
capacity candidate: 9.6 MB of CI16 payload, plus the active job and DSP workspace.
Its final bound must be established by paced replay and simultaneous recording.
A full queue is unhealthy feedback and triggers the existing fallback policy;
healthy acceptance requires zero such events. Never obtain a timing pass by
silently dropping probes or treating unevaluated work as a negative detection.

## Feedback port and identity

The acquisition producer remains the sole owner of IIO operations. A host worker
returns an immutable decision to a bounded queue; it never writes the socket or
tunes the radio. The producer sends feedback between completed refill transactions
on the owned session. Qualify the extra command/ack latency explicitly. Do not
introduce concurrent commands on the same libiio context or a second radio owner.

Add an explicit capability and versioned feedback command to libiio/iiOD and PPU.
Exact packet identifiers and byte layouts must be frozen during implementation;
an unknown capability must reject startup before capture. Existing adaptive V2
and fixed profiles retain their published geometry and behavior.

Each decision binds the session and stream generation, source visit/event
sequence, target, physical receiver, source counter interval, native and decision
sample rates, decimation phase/delay/transient policy, detector/filter identities,
and evaluated/positive/unknown status. Validate those bindings at the provider.
Reject foreign, duplicate, reordered, future or expired feedback. Scores from an
unattested receiver or incomplete source interval cannot promote a target.

Use device counters for feedback age and policy application. Host monotonic time
measures queue and compute latency; it does not replace the device clock. Test
counter extension/wrap and delayed metadata explicitly. Keep the one-second
feedback-age gate and the existing consecutive-unhealthy-result fallback latch.

## Signal-time contract

The provisional direct 161-tap linear-phase FIR has a nominal group delay of 80
native samples (8 microseconds). At phase zero, output index `k` refers to source
centre index `4k - 80`. Full causal support starts at output index 40 when the
filter resets at a visit boundary. Carry this support interval separately from
the output's nominal sample count; the first 40 outputs are not fully supported
by valid samples from that visit.

The six screen windows remain present. Boundary qualification must demonstrate
that unsupported filter samples cannot create an accepted candidate, without
discarding a whole probe to hide the issue. Reset across retunes and gaps. Do not
borrow filter history from another target or receiver. Freeze the FIR coefficients,
arithmetic, phase, candidate-support rule and source-time conversion before
opening the held-out corpus.

## Sequence to deployment

1. Carry the larger-refill baseline into feedback qualification. The 23:00
   fixed-profile attempts each lost one DMA block; CPU1 affinity also failed.
   After doubling blocks to 262,144 samples and correcting the AGC-restoration
   comparison, the 23:20 full scan passed at 95.4264% duty with zero loss.
   Preserve the counter/gap checks and qualify transport with the added feedback
   traffic. Accept the execution location and seal one complete DSP configuration and
   its reference protocol. Apply the existing response, arithmetic, synthetic
   boundary and 64-dwell held-out gates without tuning on held-out outcomes.
2. Run 300-second paced host replay, including queueing, filtering, screening,
   confirmation and feedback serialization. Require mean ≤90 ms, p99 ≤100 ms,
   bounded memory, and no growing queue or healthy overload skips. Retain all
   cases and failures, not only the fastest run.
3. Implement and test the versioned single-RX adaptive source/decision contracts,
   provider feedback port and one-owner producer wiring. Exercise every invalid
   identity, malformed feedback, timeout, disconnect, cancellation and restore
   path with fixtures before RF. A host decision failure must leave recording
   valid and produce explicitly unknown/fallback evidence.
4. Bind native-10M adaptive visits through storage, offline analysis, refinement,
   tracking, API and presentation. Test physical RX1 in payload column zero and
   actual visit timing across adaptive revisits. Verify every published asset
   against its source manifest and configuration.
5. Seal one compatible release and use the remaining RF ledger for the four
   bounded shadow/adaptive RX0/RX1 checks and first scheduled qualification.
   Require the existing duty, continuity, latency and fallback gates. Stop on a
   failure, retain diagnostics, and fix the measured cause before another check.
6. Switch between scans, verify the first scheduled capture through real browser
   output within the cadence, and retain the complete fixed-profile rollback
   bundle. Migration remains outside this work.

The current fixed-profile capture/analysis and replacement-radio checks are
reusable evidence. They do not establish feedback-port performance, adaptive
detection fidelity, or adaptive deployment readiness.
