# Generalizing the recovered ac11 region

The preceding goal turn made verified progress: published commit `3b7ee7f21`
contains a complete controlled ac11 replay with exact ordinary-baseline parity,
all 32 stage receipts, matched c arms and independently verified model-score
selection. Fitted-c error fell 55.685→1.031 km; c=0 fell 53.945→1.927 km.
This is a consumed single-scan diagnostic, not a new cohort result. The broader
0.4 km mean-error objective remains active and unachieved.

## Current work

- Inventory failed retained-region calibration across all 63 DS16, 51 DS17 and
  34 DS18 members, plus the 45 development recordings in the frozen newer cohort.
  Record every member, missing input/baseline and baseline policy version. Do not
  substitute older-model outputs for a matched B7 baseline.
- Prototype a direct bounded reduced-Hessian qualification, avoiding the serial
  scalar/coordinate/tangent experiments needed to diagnose ac11. Freeze its code,
  seeds, budgets and source closure before actual recording evaluations.
- Define a general retained-region recovery rule using calibration failure and
  ordinary model rank, independent of reference position or error. Preserve all
  original candidates, qualification gates and hard60 constraints. Retain shared
  calibration/association and matched c-arm budgets.

The first direct test is a numerical simplification on already-consumed ac11,
not independent validation. Full cohort evaluation follows a frozen integration
policy; no per-scan tuning or selective accuracy reporting is permitted. Report
frequency-fit changes separately from localization accuracy.

## Preserved constraints

Production B7 remains unchanged. No new RF collection, QNAP mutation or opening
of either closed reserve is authorized by this work. Newer development analysis
metadata must be read through a strict development allowlist and its exposure
recorded separately from immutable cohort mint receipts. At most two single-thread
numerical research workers may run; none were left running by the ac11 replay.
The stopped iteration83 search and prepared iteration92 contrast experiment
remain preserved, without automatic restart.

## Completed follow-through

Iteration102 directly qualified both saved ac11 calibration states in 46
evaluations each (0.135/0.126 seconds of refinement on this server). Iteration103
then rebuilt receiver correction from the direct prefit, qualified the fresh
postfit with the same rule, and completed the matched continuation. Its final
errors are 1.030621 km fitted-c and 1.927094 km c=0, reproducing the original
research-chain recovery. Ordinary B7 parameter vectors/objectives match exactly.
This remains one consumed diagnostic; no cohort mean has been updated.

The completed inventory covers 193 membership rows, with calibration failures in
17 DS16, 9 DS17, 6 DS18 and 5 newer development members. Iteration104 resolved
bootstrap sources for all 56 pass-level failure entries across those 37 members,
including frozen research adapters for historical cases. All 148 historical B7
endpoint bindings remain available. Source availability does not by itself prove
full model reconstruction or successful recovery.

Iteration105 completed a generic five-member newer-development pilot, selected
by calibration failure without reference errors. Three older hard60 publications
require a full unchanged B7 baseline, including all regional separation passes;
the two existing B7 publications require parity checks. New failures discovered
by those baseline runs must follow the same retained-region trigger, rather than
an ac11-specific point list. Protocol and source snapshots were frozen and pushed
in `8a52f5c73` before execution, after 23 synthetic tests passed and independent
review found no blocker. All five baselines and candidates completed in one slice
each, using at most two single-thread workers. Fitted-c pilot mean changed
11.692996→0.762109 km; c=0 changed11.784764→1.381092 km. One member improved
(the already consumed ac11 failure), four were exactly unchanged, and neither
arm regressed. These failure-selected development cases do not establish
population accuracy. Both existing B7 publications replay exactly in both arms.

All five recovered calibrations qualify, but six of30 regional final attempts
remain nonstationary and are explicitly rejected (four006, two046). All selected
endpoints qualify without fallback. Independent audit verified3078 frozen hashes.
No numerical worker remains running. Full193-member recovery evaluation remains
pending; the148-member baseline metric has not been updated. Iteration106 contains
preparation only for a separate globally fixed frequency-width sensitivity test.
