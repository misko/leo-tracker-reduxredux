# Canonical tracking constructed-control gate

This bounded stage evaluates the new native-proposal plus canonical-confirmation
detector only on the already frozen TG11 constructed controls. It does not read
new development data or reinterpret the TG11 v1078 additional decision as a
known negative.

The fixed inventory is the 32 physical controls (64 receiver rows) and the three
existing causal sequences with ten physical occurrences (20 receiver rows) from
`tg11/tg11_dataset.py`. Every cached result must pass the existing injected-truth
association gate. All 84 receiver rows require a fresh active or inactive result;
there are no unknown or skipped rows.

The sequence requirements are frozen before execution:

- the repeated identical pilot at step 1 of `pilot-dropout` and `changed-pilot`
  must use the guided route on both receivers;
- the changed-pilot final step must fail open through
  `discovery_guided_failure`, remain active and associate to the new injected
  trajectory on both receivers;
- both noise and tone dropout steps must remain inactive, with no stale pair;
- the first pilot-bearing quiet-to-pilot step must be discovered immediately;
- an all-blind execution of the same canonical detector must preserve activity
  and injected association for every sequence receiver row. It differs only by
  clearing causal state before each physical visit.

The timing diagnostic covers the complete ten-step sequence inventory and both
receivers. Input loading, hash checks, native/scorer initialization and one-time
plans are outside timing. Detector screening, proposals, every canonical score,
fallback, state work and decision assembly are inside. Run one warmup and three
counterbalanced cached/all-blind repetitions on P-core 0 with numerical thread
counts fixed to one. Restore the empty pre-sequence snapshot before each cached
repeat; repetitions never become extra visits. Commit the cached sequence once
for the scientific receipt. Report CPU and wall separately. This timing is a
diagnostic comparison within the new detector and has no 10x promotion gate.

Freeze the runner, detector, native/scorer sources, configuration, input
manifests and membership before DSP. Stop after the complete fixed control
inventory even if a row fails. The 120-second bound emits incomplete evidence on
timeout. No threshold, proposal count, state policy or sequence is tuned from
the outcomes. No real replay, holdout, RF, production or ARM work is included.
