# DSX01 model comparison: agreed evaluation v1

The user approved this evaluation and parallel implementations A, B and C in
this conversation on 2026-10-16. These are research implementations, not a
production promotion. The frozen DSX01 v1 dataset is not changed.

## Population and comparison

Use all five recordings (20,084 original observations), report the 693 frozen
challenge observations separately, and retain every missing or failed result in
coverage denominators. Candidate hypotheses in the earlier investigation are
not identity labels and must not be algorithm inputs. No new RF collection or
new detections are included.

Compare the exact saved original, an equal-budget continuation, A (automatic
track-aware timing rescue), B (trajectory-level latent identity), and C
(multiple geometry/calibration starts). The primary experiment fixes each
recording's saved candidate bank, causal TLE snapshot, physical likelihood,
timing priors and bounds. Candidate-bank expansion is a separate future arm:
the missing candidate in DSX01-014 cannot be recovered in this fixed-bank arm.

Each method gets 180 full objective evaluations and 120 wall seconds per
recording/arm initially. Proposal orbit projections, objective calls, elapsed
time and optimizer convergence must be reported. The same allowance is a cap,
not a requirement to spend unused compute. Numerical smoke tests can use lower
budgets and must be labelled. All methods may return a better feasible research
iterate, but a nonstationary iterate is never called a production-accepted fit.

## Metrics

* Association percentage: 100 times assigned/all original observations. Use
  the published maximum satellite posterior > clutter posterior classification
  unchanged. This is the association of GLRT detections, not a new raw-GLRT
  threshold or independently measured satellite-identity accuracy.
* Frequency RMS in Hz: assigned points using their selected satellites, and
  separately both endpoints on the intersection of their assigned sets.
  Also report newly assigned, lost, retained and identity-switched counts.
* Timing in seconds: common shift, per-satellite total shifts, relative-shift
  RMS/max and changes over the same ordered bank. A common-gauge change is not
  evidence that every satellite physically changed timing.
* Position in km: movement and, where recording/station binding is established,
  distance to the operator-configured station coordinates. The configuration
  is not a surveyed independent geographic truth. Never infer improved position
  from a lower in-sample frequency RMS or objective alone.
* Full-scan and outside-window regression, per-window coverage and C07 support.
* Absolute-residual CDFs with missing/unassociated outputs retained in the
  denominator; separate plots for association, RMS, timing and position.

## Excluded-data evaluation and calibration sensitivity

Test early-to-late and late-to-early prediction with held CFO values excluded
from parameter fitting, track extraction and selection. Use neutral training
seeds and rebuild the calibration without full-data fitted band contrasts.
If using the original fixed candidate bank, label this candidate-conditioned
validation: its earlier discovery saw the complete recording. Do not describe
this as an untouched end-to-end discovery test. Full-data warm-start experiments
are development diagnostics and are kept separate from these temporal arms.

All recordings have already been inspected. Recording-grouped retrospective
validation does not undo that exposure. Freeze tuning before confirmation on
previously uninspected existing recordings. DS21/DS22 remain separate position
benchmarks; DSX01 gains do not constitute gains on those datasets.

Fitted-c is the headline arm. Include the controlled c=0 arm required by
AGENTS.md with identical observations, candidate banks, other priors, initial
policies and search budgets. Report frequency and position effects separately.
The saved original is not a matched c=0 baseline; a new continuation baseline
is fitted for each arm.

## Interpretation gate

More associations alone do not establish success. Require improved excluded
prediction, preserved output coverage, and no unexplained loss of established
support outside the problem windows. Report failures, stationarity and all
regressions. No production change is authorized by this research comparison.
