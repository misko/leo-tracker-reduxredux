# Causal known-channel acceleration: experiment v1

Objective: 10× lower processing cost toward near-real-time ARM operation by
reusing a previously confirmed signal on a channel. A 10× microkernel win does
not satisfy the objective by itself: total acquisition, screening, tracking,
fallback, state and dual-receiver costs must be counted. Server results are
the first gate, not ARM measurements.

This new experiment preserves the old frozen server-evaluation artifacts.
The old holdout is exposed and is never represented as fresh validation.
New outcome-independent, longer DS5 blocks will have session-disjoint development
and fresh held-out membership. Both receivers stay with their session. The
initial native experiment supports 2.5 and 5 MS/s; higher-rate support remains
unverified, not silently mapped or excluded from the overall scope.

## Algorithm being tested

An accepted acquisition creates state keyed by session, receiver, channel, edge
and rate. State contains the source-counter pilot timing lattice, CFO and a
bounded causal CFO-rate estimate. Retunes do not preserve assumed carrier phase.
The fast path measures actual new IQ at the predicted timing/CFO using the
same full-aperture final exact and rolled-control GLRT statistic as the shared
newer native profile. It avoids blind CFO search and six-window ranking.

Every visited key starts cold. A two-second expiry, a forced discovery after
31 cached accepts (a 32-visit cycle including discovery), out-of-band prediction, failed evidence or
excessive innovation forces acquisition. A failed visit never becomes cached
absence or refreshes the cache. The reference baseline never supplies state.
Scoring at a predicted fractional epoch is labeled predicted-and-verified;
it is not a fresh fitted timing measurement. Optional local timing recovery
must be timed and labeled separately.

Initial policy: margin strictly >0.025, at least two supported frames, CFO
innovation <=8 kHz, timing innovation <=4 microseconds, CFO-rate bound
5 kHz/s. These are experimental bounds, not calibrated physical identity.
Do not relax them after held-out outcomes. Changes after development require
a new explicit configuration digest.

## Comparison and cost accounting

Reference and strategy independently process the same original IQ. Initial
acquisition and fallback use an identical blind detector build. One warmup and
three repetitions measure each stateless kernel action; causal state advances
once per actual visit. Load/hash verification and one-time plan initialization
are outside streaming compute and reported separately. Conversion/copies,
selection, scoring, local recovery and actual blind fallbacks are inside it.

The endpoint is within-visit timing/CFO-compatible reference-positive retention:
margin >0.025, valid fractional scoring/support, CFO within8 kHz, circular
timing within2 microseconds. A tracked measurement may use a different observed
20-ms window from blind ranking. This cross-window rule is declared before
scoring and is distinct from the earlier same-window acquisition experiment.
Report window changes and raw differences; the rule is not proof of physical
satellite identity or real-data truth. A baseline miss is not a noise label.

Report separately:

- sum of reference service / sum of strategy service, all visits and both RX;
- cold, cache attempt, cache acceptance, local recovery, expiry, forced discovery
  and blind fallback counts, with their full service distributions;
- hit-only speedup, explicitly insufficient for the whole-system objective;
- reference positives retained/lost/additional, synthetic controls and poisoned-
  cache/dropout behavior; unsupported and unknown cases stay explicit;
- original-arrival queue/decision age, recorded coverage and initialization.

Even zero-cost hits cannot deliver10× if >=10% of visits require a baseline-cost
blind call. A four-channel64-visit block needs at least4 cold acquisitions per
receiver (6.25%); cached hits must cost <=4% of baseline for10× overall even
before extra failures. Quiet/nonpersistent channels may dominate this bound.
No skipped measurement may be reported as a fresh confirmed detection.

## Development revisions before fresh holdout

The initial causal replay retained 36/36 reference positives but only two
predicted checks succeeded. A causal timing-rate estimate, fitted only between
independent fitted observations, raised this to twelve. Point verification
preserves the separate fitted anchor and cannot train its own timing model.
Rate learning is bounded to 50 ppm; a CFO derivative outside 5 kHz/s preserves
the preceding slope rather than saturating to a spurious derivative.

The direct-ingest V2 kernel avoids packing a receiver or converting unused IQ.
Full aperture remains equivalent to V1. Two/four-frame variants are distinct
detectors requiring independent qualification; their microbenchmarks are not
whole-replay speedups.

Scoring CFO and physical tracking CFO are separate state quantities. Blind
acquisition can report a large residual between these; scoring must preserve
the acquired NCO coordinate while identity/innovation use physical CFO. Both
predictions advance with the learned physical derivative. Only scoring CFO is
subject to the native +/-400 kHz search support. The measured physical result
must remain within 8 kHz of its predicted physical value; a large expected
residual alone is not grounds to reject it.

Every development revision has a separate configuration and result receipt.
No development result is independent validation. Fresh holdout stays unopened
until code, configuration, thresholds, dataset and native sources are frozen.

## Qualification gates

Unit-test fractional timing at huge counters, key isolation, no lookahead,
expiry, wrong-cache innovation, caller-IQ immutability, known pilots, tones,
noise and support boundaries. Compare the fast full-score primitive with the
identical native GLRT oracle at identical coordinates. Then run causal saved-IQ
development and freeze code/configuration before fresh validation.

Do not declare the10× goal complete from just a hit-only kernel result,
reduced coverage, unsupported rates, or synthetic cached seeds supplied by an
oracle. A short identified ARM saved-IQ replay is ultimately required for the
ARM processing claim. No new RF collection is authorized or needed here.
