# Two-candidate native search: fixed development comparison

The previous goal turn made progress: a complete, source-locked 64-visit replay
measured 100.06x/122.80x native blind CPU improvement and a further
1.309x/1.360x from actual causal tracking. It also exposed a material coverage
loss: 67/79 application-positive receiver identities retained despite 56/56
application-positive visits retaining an associated pair. Its receipts remain
unchanged. The next action is to spend compute on a broader native search.

Every lost receiver in that prior receipt has an application pair with its
weaker member's margin at least 0.3077 (strongest-pair minimum range
0.3077–0.5619), versus a 0.025 gate. This is not physical truth or equivalence
between statistics, but the discrepancy is not confined to marginal reference
positives. Prior native receipts retain chosen pairs, not every rejected
observation; this experiment captures observations to make search failures
inspectable without rerunning saved IQ.

## Fixed intervention

Build an isolated engine with exactly two acquisition candidates per probe
instead of one. Use the existing two-candidate capacity in the native numerical
oracle. Change only the compile-time candidate budget; preserve nuisance-tone
conditioning, acquisition support selection, fine CFO search, fractional final
exact/control score, and alternating symbol profile. Do not modify reference
checkout sources. This research build is not a production dependency or a
published contract change. Four candidates are deferred: existing arrays and
suppression logic support only two.

Keep the frozen `native_tradeoff/native_tradeoff_detector.py` controller.
Chronological pair selection considers valid candidates from each probe,
orders same-probe evidence by margin then candidate index, and requires
same-receiver nonoverlapping probes with compatible physical CFO. Adding a
candidate can change the chosen pair; previous identity retention is measured,
not assumed. Tracking confirms two prior hypotheses on fresh samples with
immediate blind fallback, two-second expiry and forced discovery after 31
guided accepts. No reference result enters state.

## Fixed methods

1. Current full application scanner, both receivers, eleven probes, ten
   acquisition candidates, same configuration as the preceding experiment.
2. Original one-candidate native blind detector using its original frozen
   binary and the unchanged controller with forced discovery.
3. New two-candidate native detector with forced discovery.
4. New two-candidate native detector with causal tracking.

The new helper also supports budget one only for an isolated build regression
against the original engine. Compare science fields excluding timings and
engine-ownership tokens. Never rewrite a golden fixture to obtain agreement.

## Membership, freezing, and bounded execution

Reuse the frozen adapter and exact development membership:

- Controls: 42 original physical cases/sequence occurrences, both RX;
  methods 2–4; 120-second execution bound.
- Diagnostic: 26 generated development physical cases, both RX; all four
  methods; 300-second execution bound.
- Recorded: 64 development visits, 32 per rate, source-time order within
  session, both RX; all four methods; 300-second execution bound.

Freeze this protocol, engine description, runner/engine and owned tests,
imported helpers/controller/dataset, manifests, original binary/build sources,
new binary/build sources, and actual application/native backend before any
outcomes. Keep common hashes unchanged across stages. Each stage writes an
immutable receipt; later stages require complete stable predecessors. Source
changes, exceptions and timeout halt dependent work. Quality differences do
not justify dropping cases or retuning the frozen variant.

Run one DSP campaign at a time on P-core 0 with numerical thread counts one
before import. Rotate method order by case, run each once per case, and advance
independent controllers once per chronological visit. Both RX are inside the
timed physical call. Include conversion, screens, candidate processing, guided
attempts, fallback and state work. A lightweight recording adapter captures
returned observations by reference inside timing; serialize after timing.
Exclude initialization, IO, hashes and assessment. Measure the application
contemporaneously rather than borrowing old CPU ratios.

No validation or original holdout IQ is opened or generated. No RF collection,
QNAP modification, production modification or deployment occurs.

## Assessment and decision

Preserve all observations, chosen pairs, margins, timing/CFO, support flags,
candidate indices, route/work counts, per-call CPU/wall and input/source hashes.
Reuse frozen truth/reference association at 2 us/8 kHz. Report known-negative
positives and injected-pilot associations; low-SNR and partial-symbol outcomes
separately; receiver presence losses separately from active identity mismatch;
visit retention separately from dual-receiver coverage. Real-data additions
remain unadjudicated, not known physical false alarms.

Compare two-candidate blind to original blind and tracking to two-candidate
blind separately. Report paired CPU sums per rate, medians and observed extrema,
fraction below 120 ms, guided success/fallback and every science disagreement.
The target is at least 10x CPU reduction at both rates. Receiver reference-loss
bands remain 0%, <=1%, <=3%, <=5%, >5%, with false positives and multi-signal
coverage alongside them. These bands are not user approval of a particular
loss. The previous 15.19% receiver identity loss is not small merely because
visit detection survives. A promising result needs independent qualification
before production replacement or completion of the full goal.
