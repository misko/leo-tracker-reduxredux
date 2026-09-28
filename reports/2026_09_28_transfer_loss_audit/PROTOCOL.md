# Fixed-fit transfer-loss and positional-gradient audit

Audit all three leave-one-dataset-out target evaluations and the all24 fit,
each against its original eight-record position fit. Reuse the six resulting
dataset comparisons, all 1,462 original eligible tracks (2,924 paired rows),
and exact sealed positions, timing offsets, training candidate weights and
stationary offsets. No fit, parameter change, new IQ, RF, catalogue propagation,
record exclusion or geographic scoring. Earlier outcomes are already exposed.

Recompute per-candidate Student-t training scores (including the existing weak
offset penalty) and held scores at the frozen points/offsets. Verify training
posteriors, full-mixture held scores and aggregate ledgers. Join receiver/channel,
training/held counts and time spans from the exact observation exports. Candidate
IDs are indices in each frozen catalogue/bank, not external NORAD identity labels;
compare them only within the identical track/bank, never across captures.

Decompose held changes by receiver, channel, recording and whether the training
MAP bank candidate changes. Stable MAP does not imply fixed mixture weights,
offsets or timing, nor a verified physical identity. Group sums must recover the
original paired loss. Report gross loss/gain separately from the net change.

For each new point, evaluate its per-track training position gradient using
training weights/offsets and central prediction differences of 1e-4 km. Require
visibility stable across perturbations. Project onto the direction from that
new point toward the corresponding original eight-record training fit. This is
local likelihood pressure, not a causal finite-deletion influence or a direction
toward geographic truth. Preserve both gradient coordinates and signed projections.

For each dataset/comparison, report the top ceil(10% of tracks) by training loss
and by positive projected training gradient, with deterministic session/track
tie-breaking. Evaluate their held contributions without changing membership.
Also show held-ranked concentration explicitly as descriptive hindsight, not
an admissible selection rule. Never remove tracks because of held losses.

Three independent dataset workers, each capped at 90 seconds/4 GiB, one thread,
nice19, sequential execution. No retries. Archive all track rows and aggregates,
commands, source/input hashes and failures. No new geographic estimate or model
promotion follows from this diagnostic. Summed all24 gradients must replay its
sealed position gradient within 1e-5; all score sums must agree within 1e-7.
