# Next bounded experiment: causal prediction and blind fallback

SOL metadata-only feasibility review; no holdout detector outcomes used.

The current search worker evaluates seeds produced independently within each
visit. That is not a test of tracking-derived timing prediction. The distinction
matters: failure of a cheap within-visit timing proposal does not falsify a
prediction from a previously confirmed signal.

## Frozen proposed state machine

Reset at each session block. Key state by receiver, channel, edge and rate.
Process strictly in recorded visit order. Only the strategy's own accepted
candidate may update state; the all-blind comparison never feeds the strategy.

Store accepted absolute pilot phase, tracking CFO and source time. For a
candidate in 20-ms window w:

```
period = rate / 750
phase = (source_start_counter + w * rate / 50
         + epoch + fractional_offset) mod period
seed = (phase - current_source_start_counter - current_w * rate / 50) mod period
```

Preserve fractional coordinates and exact source-counter differences. This
predicts the timing lattice, not carrier phase across a retune. Do not use an
integer rounded frame period for rates where rate/750 is nonintegral.

Use a predeclared 0.5-second maximum age for this feasibility experiment and a
bounded timing neighborhood with a frozen ±8-kHz CFO neighborhood. A predicted
result must complete fractional confirmation, have margin >0.025, and satisfy
timing/CFO innovation bounds (2 microseconds circular timing, 8 kHz CFO).
First occurrence, expired/missing state, failed confirmation or failed innovation
triggers the ordinary blind search. An unprocessed or missed visit is unknown,
not absence; stale state expires without an invented detection.

The current NativeDwell seeded route uses its own timing proposal. Implementing
this experiment requires exposing the existing external-epoch confirmation
primitive and, for a narrowed CFO experiment, an explicitly bounded CFO API.
Measure an external-epoch/full-CFO variant separately if no CFO seed API exists;
do not claim reduced CFO work from timing reuse alone.

## Dataset opportunity count

Each real split has 16 repeated-target visit opportunities (32 receiver
opportunities): four visits per rate, eight per edge. No signal outcomes were
used for these counts.

| Metadata-only measure | Development | Validation |
|---|---:|---:|
| Revisit start-age min/median/max, ms | 120.009 / 200.542 / 943.516 | 120.138 / 341.064 / 822.581 |
| Age-eligible receiver opportunities at 0.5 s | 26 | 24 |
| Age-expired receiver opportunities | 6 | 8 |

These are upper bounds on actual seed attempts: a predecessor must first pass
confirmation. Development per-target sequences include four singletons, eight
length-two sequences and four length-three sequences. This can test one-step
timing reuse. It cannot qualify Doppler-slope estimation, long continuity,
outage recovery or the maximum-age parameter.

## Required evaluation

Freeze code/configuration before validation; record seed attempts, strict
accepts, fallback rate, matched/lost/additional baseline positives and explicit
unknowns. Include all screening, confirmation, fallback and state costs. Sum
both receivers per visit and replay original arrival times. Preserve exact and
rolled-control treatment. A positive belonging to a different signal must not
silently suppress discovery of the reference candidate.

The current suite lacks multi-second gaps, deliberate outages, long tracks and
physical truth. If this small causal experiment succeeds, a new dataset version
should add preselected longer source blocks and outage controls. Existing
holdout results from the other experiments must be treated as exposed when
designing that next version, not reused as a fresh final test.
