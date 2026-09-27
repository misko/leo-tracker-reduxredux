# Cache reuse after the TG11 screen-coordinate failure

This is a design for one bounded follow-up experiment. It does not revise the
frozen TG11 implementation or its failed scientific gate, and it makes no new
sensitivity or 10x claim.

## Decision

Remove the lag-differential rank epoch from the cached route. A trusted prior
positive pair already supplies two probe positions, frame phase, a scoring CFO,
and a measured physical CFO. On the next compatible visit, predict those same
two nonoverlapping probe positions in integer source-counter coordinates and
run the repository's canonical `conditioned_glrt64_score` at the floor and
ceiling of each predicted local epoch. Two fresh canonical confirmations form
the new positive pair. Any failure immediately falls open to discovery.

The rank screen may remain a diagnostic value, but it cannot select, reject, or
move a cached confirmation. The frozen audit establishes that its approximate
lag-differential epoch is not calibrated to the refined acquisition epoch; a
stable but uncalibrated screen is still unsuitable as a 4 microsecond gate.

Cold discovery must initially remain the unchanged application acquisition and
canonical confirmation path. It enumerates the full positive-pair inventory
and establishes cache state from its own fitted candidates; those candidates
are runtime detector outputs, not an offline oracle. Native proposal plus
canonical confirmation is a plausible cheaper discovery experiment, but the
frozen diagnostic already shows that it does not preserve the current decision
objective: on the failed
`newdev-r2500000-scan-fw-40ebc07665464c7d-v001078`, where the unchanged
application comparator had no positive pair, the current canonical scorer
passes the native coordinates at integer epochs 7 and 9 with margins 0.1356
and 0.1168 and CFO-consistent results. The application top-ten acquisition was
48-50 microseconds and 84.7 kHz away from that identity. This is evidence of a
different proposal/sensitivity set, not evidence that the frozen extra should
be relabeled. The result is pinned by `tg11_diagnostic/results.json` SHA-256
`da5f8f0ef77d56e6993bbad926d2318fea69b4fa2614d76e2935ea0c3e58bf21`.

Therefore native-proposal discovery is rejected under the current gate. It may
be studied later only under an independently defined truth/false-alarm
objective frozen before a new dataset. The cache-path experiment here retains
the old failure gate and cannot use that later objective retroactively.

## Causal state and route

State remains keyed by continuity/session, receiver, channel, edge, sample
rate, tuning identity, and calibration identity. It stores:

- the two probe indices from the last application-discovered and canonically
  confirmed positive pair;
- each selected canonical epoch as an integer source counter plus a bounded
  fractional prediction remainder;
- the scoring CFO and the measured physical tracking CFO;
- timing and CFO rates derived only from data-selected proposal/confirmation
  measurements, never from a projected rank epoch or an oracle comparator;
- the last independently measured source time, a two-second expiry, and the
  count of accepted guided visits since discovery.

Large source counters never become floats. Prediction first subtracts integer
counters and then adds the bounded fractional remainder. Retune, continuity,
session, rate, edge, or calibration changes select a different key.

For one receiver visit:

1. Route directly to unchanged application discovery when state is absent, older than two
   seconds, incompatible with the visit geometry, or has 31 accepted guided
   visits. The next visit after 31 guided accepts is the forced discovery.
2. Otherwise project the last accepted pair's two probe indices and fitted
   source epochs into the new dwell. Do not run or inspect the rank screen.
3. At the first probe, convert that one natural CI16 receiver aperture and call
   `conditioned_glrt64_score` at the floor and ceiling of the predicted local
   epoch, deduplicating an integral prediction. This is the same 64-symbol
   exact/control statistic and nuisance fit used by the application comparator.
4. Treat each point as a candidate. Require margin at least 0.025 and compare
   its returned tracking CFO with the causal physical-CFO prediction within
   8 kHz. When both points pass, deterministically select higher margin, then
   lower epoch on a tie. The selected point must be within 2 microseconds of
   the causal prediction. No rank score participates.
5. If the first probe fails, run discovery immediately. If it succeeds, apply
   the same canonical check to the second stored probe. The two probe starts
   must remain at least 20 ms apart, and their measured tracking CFOs must agree
   within 8 kHz.
6. Only two successful fresh probes emit active. Update state from the selected
   integer epochs and measured physical CFOs. A failed guided attempt never
   advances or clears the prior fitted state; the following discovery result
   either replaces it with a new application-confirmed pair or returns inactive.

This is at most two guided probes before success and at most one guided probe
before an early failure. A fallback includes the attempted work in whole-call
CPU and wall time. No failed or unattempted visit is relabeled as a measured
negative.

Selecting between floor and ceiling is a bounded one-sample local timing
measurement. It does not justify a wider recovery claim. If the predicted
epoch is integral and only one point is scored, retain the prior timing anchor
and use the score only as fresh presence/CFO evidence; do not pretend the input
epoch was re-estimated. A later discovery refreshes the fitted timing state.

Using the prior pair's probe locations preserves the prior observation's dwell
region without claiming that a signal must remain there. A moved, appeared, or
disappeared signal simply forces discovery. The discovery result is the only
way to establish a new hypothesis outside the local recovery neighborhood.

## Why the frozen native guided result is insufficient

The current guided TG11 wrapper is not sufficient unchanged. It passes
`recover=0` to known-state V3
(`tg11/tg11_native.c`, lines 145-154). Known-state V2 then normalizes and scores
the predicted epoch directly; with recovery disabled, the returned epoch is
the normalized prediction, not an independent timing fit
(`native/known_state_v2.c`, lines 72-79 and 114-125). TG11 also hardcodes the
observation as not fitted (`tg11/tg11_native.c`, line 157). If this scorer were
used for timing, it would have to pass `recover=1`, require
`timing_bracketed`, and expose that status through the port. That recovery
evaluates predicted timing and its one-sample neighbors, accepts only a
center-bracketed peak, and performs bounded parabolic refinement
(`known_state_v2.c`, lines 79-112). The preferred canonical design instead
uses the explicitly frozen floor/ceiling point rule and does not consume the
native fitted epoch or native margin.

Its physical CFO is independently estimated, conditionally on the scoring center.
The final GLRT derives a residual from the observed per-symbol correlation
spectrum; V2 reports `tracking_cfo_hz = scored_cfo_hz + residual`
(`known_state_v2.c`, lines 120-127). V3 compares that measured tracking CFO to
the causal physical expectation (`known_state_v3.c`, lines 16-26). The expected
physical CFO is not copied into `tracking_cfo_hz`. It does constrain the call:
expected and scored CFO must be within the GLRT's half-symbol-rate residual
support (`known_state_v3.c`, lines 5-17). Therefore the result is a local
measurement around the scoring center, not a global acquisition.

The preferred cache experiment uses the canonical Python scorer, whose API has
no expected-physical-CFO input. It returns tracking CFO as its acquired/scoring
center plus an observed residual; the controller compares that result with the
causal expectation afterward. This makes it impossible for the expectation to
be echoed through that API. Qualification must still offset the scoring center
on both sides of injected truth and require the returned tracking CFO to land
within 8 kHz. Noise and tone must not become positive merely because the
scoring center is close.

The V3 audit remains useful as a railguard if a later native canonical scorer
is written: for fixed IQ, timing, and scoring CFO, varying only
`expected_physical_cfo_hz` must leave `tracking_cfo_hz` unchanged while only
innovation/status changes. No current native GLRT score may be substituted for
the canonical decision in this experiment. The native final scorer alternates
symbol regions and carries build-profile nuisance behavior that the current
application `conditioned_glrt64_score` does not share.

## What the fixed counter sequence can exercise

The frozen 64-visit development prefix contains 32 physical visits at each
rate. Each rate/session has four channel keys. Counts and source-counter gaps
are:

| Rate | Per-channel visits | First/cold visits | Later visits with gap <=2 s | Gaps >2 s |
|---:|:---|---:|---:|---:|
| 2.5 Msps | 9, 10, 7, 6 | 4 | 28 | 0 |
| 5 Msps | 4, 14, 8, 6 | 4 | 28 | 0 |

Including receiver in the key gives eight first/cold receiver visits and 56
temporally eligible later receiver visits per rate. These are upper bounds on
cache attempts: a key still needs a prior accepted signal, and quiet or changed
channels remain blind. The largest channel history has 14 visits, so this
prefix cannot exercise the 31-guided/forced-next cadence. A separate
constructed 33-positive-visit causal sequence is required for that policy
test. It must reuse frozen IQ with explicit source-counter and carrier-phase
mapping, as the existing TG11 sequences do.

The metadata also exposes an important whole-call bound. If discovery used the
full application call, four first channel visits out of 32 already consume
12.5% of application cost; even free hits could reach only 8x on this prefix.
Phase one's native all-blind calls cost about 1.06% of application CPU at
2.5 Msps and 0.81% at 5 Msps, and a 22-proposal by two-point canonical layout
was estimated around 40 ms. The diagnostic shows why cost is not the blocker:
that proposal route changes the accepted identity set and preserves the exact
frozen extra. Its 94.5x/122.8x cost ratios cannot enter an attainable 10x claim
under the current scientific objective.

With unchanged application discovery, the cache mechanism alone cannot reach
10x on this 32-visit-per-rate prefix: the four cold channel visits consume
12.5% of baseline cost, imposing the 8x ceiling above. A whole-call 10x result
therefore also requires at least a modest exact-output acquisition optimization
on discovery visits, or a longer preregistered workload with a lower cold
fraction. Parallel wall-time alone does not reduce the required process CPU.

## Minimum implementation experiment

Implement a new research-only adapter rather than modifying frozen TG11 files:

- `canonical_points(raw, receiver, probe, proposed_epoch, scoring_cfo)` converts
  one 20 ms aperture and calls the unchanged repository scorer at the unique
  floor/ceiling epochs. It returns every exact/control/margin/residual result
  and timing, with no threshold inside the adapter.
- `discover(raw)` initially calls the unchanged application analyzer with ten
  candidates, 11 probes, and both receivers, then deterministically reconstructs
  its full positive-pair inventory for state initialization.
- A small causal controller stores the last canonical pair and calls
  `canonical_points` on exactly those two nonoverlapping probes. It never calls
  the rank screen on the cache path.
- A guided failure invokes discovery once. No guided score is reused as a
  discovery proposal and no application comparator observation enters state.

The first experiment is cache-path-only: use unchanged application discovery
to seed state, then exercise the two-probe canonical reuse path on component
controls and the three existing causal control sequences. It should stop
before real timing or replay on any failure. Native-proposal discovery is not
part of this experiment because the completed diagnostic already violates its
governing gate. There is no reason to build a new rank transform,
multi-hypothesis cache, or broad parameter sweep for this question.

## Required gates

Before any saved real-IQ outcome run, component tests must cover:

- exact probe bounds and RX1 terminal addressing at both rates;
- floor/ceiling deduplication and tie order, fractional predictions at 0 and
  +/-0.49 sample, zero energy, and no NaN/Inf output;
- canonical parity with direct `conditioned_glrt64_score`, scoring-center
  offsets, signed residual direction, and CFOs near +/-399 kHz;
- known pilot, noise, tone, strong tone plus pilot, two close pilots, timing
  switch, CFO switch, dropout, retune/continuity reset, and stale state;
- one successful probe never emits active; any invalid or nonpositive probe
  falls open exactly once; two probes must be nonoverlapping and CFO-consistent;
- source counters above 2^53, input immutability, deterministic repeats, expiry,
  key isolation, and the constructed 31-guided then forced-discovery sequence.

The staged scientific gate must then retain the existing application objective:

1. Run all frozen negative and injected controls and the fixed causal sequences.
   Every active pair must associate on the same receiver; noise and tone remain
   inactive. Record all attempts, fallbacks, and statuses.
2. Re-run the four fixed phase-one visits with application discovery. The former
   `v001078` visit must remain inactive, and every application-positive visit
   must remain active with an associated pair. Do not change thresholds,
   discovery proposal source, or membership after observing it.
3. Only after those pass, freeze a development replay. Compare with the
   application's complete ten-candidate, eleven-probe, both-receiver response.
   Require zero extras, zero losses, and association within 2 microseconds and
   8 kHz. Report guided success, guided failure, cold, expiry, periodic
   discovery, and blind-positive/negative routes separately.
4. Measure complete CI16-to-decision CPU and wall, including both receivers,
   floor/ceiling scores, failed guided work, conversion, and discovery fallback.
   Require at least 10x whole-call CPU speedup independently at 2.5 and 5 Msps;
   report per-hit cost separately without substituting it for whole-call cost.

The original holdout remains unopened until the source, configuration,
membership, and all gates above are frozen. Passing development would justify
one held-out run; it would not establish deployed or ARM performance.
