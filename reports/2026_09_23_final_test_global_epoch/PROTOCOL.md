# Once-only final TEST protocol: selected global 0.2 s rule

The frozen two-group validation selected the conditional global epoch estimator
with regularization scale 0.2 seconds. Evaluate exactly the 64 scans in the
complete-inventory TEST partition as nested 1, 6, 16, and 64 scan views from
both original Sacramento 250 km and Reno 500 km priors.

For each view/start, first run the unchanged blind tau-zero catalogue search
using the published 100-to-0.1953125 km grid and beam width 3. This baseline is
initialization and fixes identities; it is not an alternate primary TEST model.
Then fit only one global epoch shared by all selected tracks at scale 0.2 s,
with the frozen ±5 s bound, per-track constant CFO, duration weights, capped
800 Hz loss, training masks, and accepted Schur stopping rules.

Export only exact TEST membership with four read-only workers and verify all
cache hashes. Seal all eight baselines before fitting all eight selected-model
arms. Seal every fit before complementary-row and reference evaluation. Retain
all failures, nonfinite, out-of-prior, visibility-invalid, boundary, or
stopping-rule failures. No alternative scale/model, tuning, retry based on
outcome, deployment, RF collection, or production change is permitted.
