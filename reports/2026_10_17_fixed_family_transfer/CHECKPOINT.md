# Fixed-family transfer and clipping checkpoint

This goal turn made concrete progress. The new fixed-assignment research kernel
and diagnostics preserve every selected curved observation and candidate label,
exclude all linear members from calibration, and reveal a real phase-clipping
failure in S01. The larger association / <0.5 km goal remains active and
unachieved. No RF was collected, QNAP was not modified, no commit/push performed.

## New verified findings

- Default fixed-family transport: common c0 blind labels/initializers in both c
  arms, 1519 curved points / 43 fragments in S01 and 1123 / 29 in DS22-001.
  Merged S01 calibration uses 36 constants; DS22 stays at 29. All points retain
  Gaussian cost even when a residual gate fails. No candidate label switches.
- At GPS, S01 NORAD 100320 hits phase -3 s, and two drift bounds hit +1 Hz/s.
  Phase-box release alone reduces pooled S01 RMS ~148 -> 132 Hz. Drift-box
  release alone does little. Both releases preserve Gaussian priors. This does
  not remove the remaining geographic discrepancy.
- A strict frozen-hardware test changes only satellite 100320's phase from -3
  to -3.7 s. Three measured-curved RX2 fragments (CH1 T002 25 points, CH2 T001
  43, CH4 T000 73) calibrate the shared phase. Linear CH7 T005 and CH8 T002,
  16 points each, associate afterward. No linear calibration or extra drift.
- This adds 173 points at known GPS in both c arms: 2009 -> 2182, 45.49% of all
  4797 raw GLRT detections. Zero lost or relabelled old IDs. The 2009 baseline
  includes eight candidate-after-gates gains over the earlier 2001 repair.
- Full prepared causal-bank competition: 1707 candidates, 601 phases from -15
  to +15 s for unsupported candidates, supported phases locked, unchanged
  Gaussian priors. Only 100320 passes all three arcs in either c arm. Passing
  phase samples -3.90 to -3.60 s (seven samples) are a gate range, not a CI.
  All scalar 601-state costs and passing flags match the full candidate-vector
  scores numerically. This is not authenticated identity or a continuous/global
  uniqueness proof. Finite candidate bank and same-data conditioning remain.

## Independent fixed-family searches (all terminal)

Searches never read GPS transfer/phase-repair outputs. Common earlier blind c0
families and source position seed both c arms. Every location uses exact phase
geometry; 3x3 +/-16 km grid and binary 8..0.0625 km scales, two sweeps each,
maximum 73 locations. Binary scales avoid an under-refinement problem possible
with factor-four scales and only two sweeps, verified on a synthetic 2D minimum.

| Case / model | c0 error km | fitted-c error km | Extended points c0/fc |
|---|---:|---:|---:|
| S01 separate constants | 6.355511 | 6.355511 | 2436 / 2436 |
| S01 merged constants | 6.479286 | 6.479286 | 2436 / 2392 |
| S01 separate, phase floor 15 s | 6.355511 | 6.355511 | 2436 / 2436 |
| DS22-001 separate | 2.139302 | 2.139302 | 1515 / 1515 |

S01 improves from the prior 8.37/8.50 km noise-gated result; DS22 is worse than
the prior 1.895 km fitted-c result. Some fitted curved members fail final noise
checks, so these Gaussian fixed-family searches are exploratory rather than
qualified localization outputs. Full-bank association happens only after
saving the location, without feeding labels back. No selected source curved
fragment changes NORAD in that extension. Scores across different Gaussian/
clutter criteria or merged/separate weight caps are not directly comparable.

## Artifacts, tests and provenance

README.md includes all diagnostic/search tables, phase profile and association
figures. Scalar phase profiles, full candidate matrices, original IDs, bounds,
priors, exact fits and original point ownership are retained.
44 focused tests pass, including independent dense Gaussian point LS, immutable
labels, no bad-member cost clipping, linear exclusion, per-candidate phase-prior
accounting and 2-axis search refinement. Current handwritten sources pass Ruff.

Earlier default transfer and Gaussian-search kernel versions are preserved in
baseline_code_snapshot. audit_run_source preserves the exact all-bank audit
script used at runtime. A later lint-only explicit binding of immediate loop
callbacks does not change numerical execution. Current sources are separately
snapshotted; protocol hashes bind versions and durable inputs. Earlier sealed
reports are unchanged. All bounded process handles have been polled terminal.

## Next work

Audit the clipping pattern on other scans, requiring joint support from several
measured-curved arcs, unchanged Gaussian priors, frozen established hardware and
old assignments, full candidate competition, and explicit linear-only transfer.
This can increase true-GPS coverage without claiming better localization.
For remaining position bias, verify RF/timing input authority and shared
receiver/band residual structure before granting per-track nuisance slopes.
Current best DS22 figure remains 1.895 km; full DS22 and all-scan independent
position validation are incomplete. No repeated external blocker exists.
