# Full saved-scan coarse-cutoff ablation

User authorized replay of the full DS9 scan with the coarse cutoff disabled,
followed by the same tracker, comparison of recovery and extra outputs, and
ARM timing. This is a saved-data experiment with no RF collection or production
activation.

- Input: all 2,215 original 120 ms dual-RX dwells from
  `scan-fw-f363c7f29141d0b1`, 2.5 MS/s, first 20 ms/RX, unchanged raw bytes and
  event/counter authority. Compare every raw hash to the original run.
- Detector: frozen diagnostic binary from the prior 85-dwell experiment,
  differing from optimized ordinary only by disabling the preliminary coarse
  score rejection. Final GLRT margin >=0.025 remains unchanged.
- Hardware: physical PLUTO+ 192.168.1.15, serial batches of 16, same persistent
  RAM benchmark. 40-minute experiment bound; no concurrent device jobs.
- Baseline: frozen original full-scan ARM detector and frozen maintained
  server detector/tracks. Do not regenerate or change oracle fixtures.
- Tracker: identical rolling-backfill host and ARM binaries and defaults.
  Three host repeats; three physical tracking repeats after detector replay.
- Projection: maintained integer-epoch support geometry, same UTC authority.
  Validate the report's projection against all original 9,728 observations.
- Evaluation: reuse shared membership comparator and thresholds. Exclude only
  approved ref #10; 62 reviewed references. Duration buckets <15 s, 15–30 s,
  >=30 s. Report gains and losses, the five targeted long references, output
  counts, and original passing-candidate inclusion.
- Extra outputs: report hypothesis counts and consistency with any reference
  track. Such counts are neither unique physical trajectories nor established
  false positives. Full-scan same-source circular CFO agreement with server
  passing candidates is an additional diagnostic, not truth or one-to-one
  candidate matching.
- Timing: detector mean/median/p95/max, summed detector time, and counts >=120
  ms; tracker separately. Staging time is not detector time. Saved-data replay
  is not continuous-acquisition qualification.

No scientific thresholds or detector settings will be tuned during this run.
