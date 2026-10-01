# Bounded rolling backfill prototype

User-approved proposal: keep the frozen chronological rolling linear tracker
and add a bounded retrospective extension when a track is confirmed. Proposed
bounds are 32 seconds of available history and at most 16 seconds before the
track's current beginning. Initialize from its earliest local linear fit;
use original candidate timestamps, lane-normalized CFO/alias spacing, existing
gap/gate rules, and bounded ambiguity. Keep forward prediction independent.

This experiment targets the observed initial-point losses in refs 12/48/51/52.
Reference labels are evaluation-only. No new RF, firmware changes or production
activation. Only ref10 is excluded from reviewed agreement; preserve all other
frozen thresholds, including the known ref35 source-purity limitation.

Acceptance checks:

- All four target references complete under unchanged matching criteria.
- No loss of a previously represented reference on either input set.
- Report hypothesis count and source-purity/fit changes, not only recovery.
- Preserve both known synthetic curves and check meaningful component cases.
- Physical PLUTO+ output agrees with host; three ARM-input timing repeats.
- Target <=20% increase over frozen rolling 1.11931 s reconstruction median
  (1.343172 s), with whole-process time separately reported.

Use both frozen server and ARM GLRT observation sets for the same 300-second
DS9 scan. Short/medium/long refer to server durations <15 s, 15–30 s, >=30 s.
The original rolling baseline represents 39/62 using ARM input (3/9 short,
17/25 medium, 19/28 long) and 58/62 using server input. Root shared evaluator,
causal fit diagnostic, known synthetic truth, host runner and device runner
are reused without altered thresholds. Qualification artifacts may reside in
the prior report's `qualification/rolling-backfill` directory to preserve the
existing runners; this report links their exact receipts.

A batch implementation must state whether it emulates availability at first
confirmation or uses future evidence. Passing replay tests does not qualify
a bounded-memory live service. If original hypotheses are retained alongside
extensions, label this explicitly; preserved coverage would then be a bank
property, not demonstrated exclusive assignment correctness.
