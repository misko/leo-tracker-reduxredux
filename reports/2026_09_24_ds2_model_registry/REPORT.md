# DS2 positioning model registry

This is a read-only inventory of every earlier positioning model worth
considering for DS2. It does not run a model, alter a cache, or use a reference
position. The machine-readable source of truth is `model-registry.json`.

## DS2 comparison set

Run these as the primary predeclared DS2 comparison set:

1. `baseline_doppler` — tau-zero ordinary full-observation Doppler matching.
2. `shared_global_receive_time` — one bundle-wide timing nuisance.
3. `causal_per_norad_orbit_rate` — hard association plus causal rate and exact
   replay.
4. `equal_weight_joint_multiscan_position` — one coordinate jointly selected
   across independent whole-session DS2 groups.

`regularized_per_scan_time`, `rate_aware_joint_geographic_screen`, and
`consistent_cap800_joint_objective` are valid conditional comparators when
their priors, seeds, candidate budget, and loss are frozen before DS2 runs.
`shared_norad_rate_joint` is conditional on selected satellites actually
overlapping across DS2 groups. DS1 had zero overlap, so it could only verify a
block-diagonal equivalence there.

## Models that should remain secondary

Independent per-track timing is diagnostic-only: its unconstrained times hit
boundaries and did not transfer on DS1. Soft identity mixtures have a
reference-free implementation, but their probabilities remain uncalibrated and
they lack a DS1-wide independent location qualification. The AR(1)+Student-t
residual rerank worsened one DS1 group. The original simultaneous session-scale
L-BFGS-B arm is rejected because every candidate failed to converge; DS2 should
use only the repaired block-coordinate session-scale runner.

The LNB geometry work is valuable, but it is currently a geometry and
association stress test. Pointing-cone, fixed-hard-cone, and staged-width
experiments establish support behavior under an upward-pointing mount model;
they do not calibrate antenna gain, RX-to-LNB mapping, or geographic accuracy.
The local fitted-cone grid is the only existing geometry arm that searches
position, and it lost to ordinary Doppler for every DS1 full-FOV setting.

## Cone coverage

The registry distinguishes full FOV from half-angle. The staged full-FOV
implementation covers **10, 20, 25, 30, 40, 50, 60, 70, 80, and 90 degrees**.
The local geographic fitted-cone grid covers **10, 20, 25, 30, 40, and 50
degrees**. The historical fixed-hard-cone experiment instead uses half-angles
of **10, 15, 20, and 30 degrees**.

For DS2, use the local cone widths through 50 degrees as a predeclared
secondary sweep. Do not infer a narrow beam from a low supported-only RMS: all
tracks, including unsupported tracks through their penalty, must remain in the
objective. Preserve both symmetric RX-to-LNB mappings unless an independent
hardware calibration breaks the symmetry.

## DS2 prerequisites

Every accepted DS2 inference needs a frozen manifest/partition, a blind prior,
receipt-bound causal caches and TLE archive, exact replay gates, and separate
post-seal evaluation. Keep all tracks from a recording in the same outer
partition. Freeze nuisance priors, grids, beam widths, candidate/finalist
budgets, and group weights before examining DS2 geographic errors.

The exact code/report locations, model-specific prerequisites, and scientific
status are recorded in [model-registry.json](model-registry.json). The registry
also names the unsupported soft-global-time-plus-rate combination so it cannot
accidentally enter DS2 scheduling.
