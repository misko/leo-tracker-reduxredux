# September 24 phase-to-satellite association artifacts

- `summary.json`: frozen protocol, primary results, 32 random-split sensitivity
  runs per track, orientation feasibility results, and provenance.
- `phase-advance-evidence.json.gz`: extracted adjacent-frame pilot phase rows.
- `glrt-timeline.json.gz`: full fractional-GLRT candidate inventory for the five
  300-second scans.
- `phase-vs-time-300s.png`: selected-track random-held phase on the left axis
  and the exact RX0/RX1 reconstructed de-aliased GLRT tracking CFO relative to
  each receiver median on the right axis, overlaid on the 300-second scan clock
  and coloured by RF channel.
- `glrt-vs-time-300s.png`: complete per-receiver GLRT margins over the scan
  clock, with passing candidates coloured by RF channel.
- `standard-adaptive-cfo-trajectories-t1.png` through
  `standard-adaptive-cfo-trajectories-t5.png`: verbatim standard adaptive
  four-channel RX0/RX1 CFO trajectory plots for each capture.
- `standard-adaptive-trajectories.json`: source sessions, analysis bindings,
  byte counts, and digests for those standard plots.
- `phase-difference-vs-time-300s.png`: every saved per-block conditional
  RX1−RX0 phase estimate, coloured by channel on the full scan clock.
- `phase-difference-timeline.json.gz`: the points plotted in that figure.
- `t1-phase-difference-vs-time.png`: zoomed T1-only phase differences with
  per-dwell circular means.
- `t1-phase-difference-summary.json`: ordinary 2π circular `R` overall and by
  dwell for the T1 plot.
- `candidate-score-by-track-receiver.png`: receiver-level train and held scores.
- `joint-receiver-candidate-score.png`: equal-weight RX0/RX1 candidate scores.
- `held-phase-association-summary.png`: held modulo-π R, controls, and contrast.
- `baseline-orientation-held-test.png`: train-fitted phase-rate orientation and
  random-held comparison with a constant-CFO control.

All catalogue labels are conditional causal-TLE candidates. No artifact claims
satellite identity or a calibrated electrical baseline orientation.
