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
