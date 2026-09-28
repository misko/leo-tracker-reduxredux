# Constrained nominal beam: calibration leave-one-record-out comparison

## Question and scope

Test whether a shared, monotonic nominal beam response transfers better than the
previous freely fitted tilt interactions. Use only the original six calibration
recordings. In each of six folds, fit on the other five recordings' reception
windows and score both periods of the omitted recording. This is development
cross-validation on an already-explored calibration cohort, not a new blind
confirmation. Do not score the original four evaluation recordings or DS8 here.

## Matched response models

Keep the proven short-horizon orbit-increment target kernel and causal reference
unchanged. Rebuild the joint background and nuisance feature scaler using each
fold's training reception windows only. Physically remove all held and omitted-
record windows before training preparation.

Let u and e denote raw LOS up and east. Subtract their per-lane, per-nominee
reception forecast means; carry those means into the held period. Define one
common scale s as the RMS of centered u over training reception windows and
nominees (duplicating receiver views does not change it); if s<1e-12 use 1.
Do not separately standardize east and up before combining them.

- D: existing three nuisance terms, without geometry.
- E: D plus centered u/s, representing co-pointed receivers.
- B: D plus [cos(10 degrees)*centered u + receiver_sign*sin(10 degrees)*centered e]/s,
  with receiver_sign -1 for RX0 and +1 for RX1.

E and B each have exactly one geometry coefficient, constrained to [0,12], with
the existing standard-normalized prior SD 0.5. Their shared slope is monotonic
in the nominal boresight dot product. D nuisance priors and all occupancy/time
constant priors and bounds remain unchanged. Fit two starts per arm: neutral and
the same fitted D start padded with zero slope for both E and B. Use the existing
L-BFGS-B limits and positive-MAP-versus-exact-null selection rule. Preserve every
optimizer receipt; no post-outcome hyperparameter or mapping selection.

This within-lane response models variation around scheduled reception geometry.
Centering removes absolute beam offsets; the experiment does not estimate a
calibrated antenna gain pattern. The ±10-degree convention and software receiver
mapping remain nominal/provisional.

## Frozen controls and endpoints

Score B with receiver-sign swap, within-role geometry reversal and a cyclic
nominee permutation of the beam feature. These must leave frequency signal,
reference, visibility and priors unchanged. Also score zero and reversed orbital
increments under the unchanged fitted B coefficients. No current observation
may enter either predictor before its score. Preserve empty candidate sets.

Primary contrasts: B-E (incremental nominal tilt), B-D, B-reference and B versus
each control, equal-weighting the six omitted recordings after normalizing each
by its own window count. Report reception and later periods separately, all
record-level signs, feature scales, fitted slopes and optimizer-bound behavior.
Do not promote a tilt or identity claim merely because orbital prediction beats
the frequency reference. Require transfer across recordings and specificity to
correct receiver/candidate geometry before choosing a future confirmation panel.

## Execution

Each fold is bounded to 120 seconds, one numerical thread and 4 GiB. Freeze this
protocol, sources, tests, launcher and input bytes before running. Preserve failed
or incomplete folds rather than silently replacing them. Run component tests,
training-isolation checks and an independent numerical/score audit. No RF
collection, IQ reprocessing, new propagation, candidate reranking or QNAP mutation.
