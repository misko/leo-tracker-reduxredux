# Adaptive blind-search cadence: development result

## Result

Neither tested minimum interval reaches the 10x compute objective, even after
accepting many unknown visits. The descriptive server ratios are 2.56x for the
1 second policy and 7.84x for the 5 second policy. They cover 24/36 and 6/36
reference-positive receiver-visits respectively. The remaining reference
positives are explicitly unknown, not detector misses or absence evidence.

| Minimum per-key blind-search interval | Blind searches | Fast checks | Unknown visits | Reference-positive visits covered / unknown / lost | Descriptive CPU ratio | Blind-cost-only descriptive ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 second | 100 | 27 | 150/256 | 24 / 12 / 0 | 2.557x | 2.600x |
| 5 seconds | 32 | 17 | 224/256 | 6 / 30 / 0 | 7.839x | 8.098x |

The last column sets measured state and fast-check cost to zero while retaining
the observed scheduled-blind cost. Even this conditional ratio is 8.10x for
5 seconds. The offline full-coverage baseline timing comes from the earlier V4
receipt, while candidate timing comes from this run, so these are provisional,
unpaired timing comparisons rather than robust paired performance claims.
Reduced coverage cannot be presented as detector acceleration or completion of
the full-coverage goal.

## Causal policy

The schedule is keyed by session, receiver, channel, edge, and rate. Every key
starts cold and performs one blind search. Later searches run at the first
recorded visit whose source counter is at least 1 or 5 seconds beyond that
key's preceding blind search. These are minimum intervals, not periodic search
deadlines or maximum-latency guarantees. Channel gaps and episodic signals can
delay or prevent discovery. Decisions use current and prior counters only.

Between blind deadlines, an eligible state runs a fresh V3 partial-two-frame
known-state measurement on current IQ. An accepted measurement may update the
unchanged tracker. A failed measurement, absent state, expiry, or forced
discovery produces an unknown result and does not trigger an early blind
fallback. No previous positive is emitted on such a visit.

The 5 second cadence exceeds the tracker's unchanged 2 second expiry. Its 224
unknown visits include 32 `expired_unknown` visits. Once a check fails and no
accepted measurement refreshes state, the tracker can expire well before the
next blind deadline. This is part of the measured tradeoff, not a detector
negative.

The frozen development V4 replay supplies independent reference observations
and baseline costs only. Reference results never seed a blind proposal, the
cadence schedule, or tracker state. Strategy blind searches rerun the common
native detector on saved IQ. Each kernel action uses one warmup plus three
timed repetitions; causal state advances once.

## Coverage and discovery latency

Seven keys have at least one reference-positive visit. Under the 1 second
policy, five are strategy-positive on the same visit as their first reference
positive and two are never discovered later in the recorded block. Under the
5 second policy, four are strategy-positive on that same visit and three are
never discovered later.

Consequently, all finite observed first-reference-to-first-strategy lags are
zero. This does not show zero discovery latency or establish 1/5 second maximum
latency. The saved sequence contains no key with a later successful discovery
from which to estimate a positive lag; channel gaps and missed episodic signals
instead leave two and three keys never discovered. A longer interval-specific
dataset would be needed to estimate a latency distribution.

Real observations are unlabeled. The 36 reference-positive visits are outputs
of the frozen detector and are not ground truth. `Lost` remains zero because
all uncovered reference positives occurred on visits with no usable fresh
strategy result and are therefore counted as unknown. This preserves the
distinction between missing evidence and measured negative evidence.

## Cost accounting

For 1 second, the strategy uses 220.712 ms blind CPU, 1.015 ms fast-check CPU,
and 2.669 ms state CPU, versus 573.787 ms for offline full-coverage service.
For 5 seconds it uses 70.856 ms blind CPU, 0.647 ms fast-check CPU, and 1.695 ms
state CPU. Wall results are 2.567x and 7.884x respectively.

The baseline and strategy timings were collected in separate runs, so these
ratios are descriptive and provisional. They are server timings, not ARM
qualification. The experiment opens no holdout IQ, performs no RF collection,
and does not change production code.
The user's acceptable discovery-latency and unknown-coverage tradeoff remains
unanswered, so neither reduced-coverage policy is promoted.

## Tests and receipts

Four tests cover source-counter scheduling and key isolation, prefix causality,
unknown-versus-loss classification, state/check cost on unknown visits, absence
of stale positives, discovery lag, and never-discovered keys. The runner verifies
dataset, reference, configuration, native binary, build receipt, and source
hashes before and after replay.

- Configuration SHA-256: `b59178d3116f726311f8cafc079c51b4d53b7caef803f62a32b76cf66248b94c`
- Runner SHA-256: `2aeff7fbdc34aa1ce362271ea674911d767d75e9219c05a98df7bd3ed5a67a9d`
- Results SHA-256: `593b5cb178647b41348c09eaa00700b974b3ca75786579f98857328c7d5e28e9`
- Offline development reference SHA-256: `6f46c25db42c37f1eb1684369ec0ff7410a5d327e8c8c133a310ea09123522a9`
- Development dataset SHA-256: `4874540dfe94bd5ced2d5496d6c53635de22c8f5d59d8edf0a159c62a899d401`
