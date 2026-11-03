# Bounded global tracklet/path association prototype

This frozen replay generates lane-local, whole-NORAD paths by dynamic programming,
then solves exact peak-exclusive set packing over that bounded proposal set. It is
therefore a global optimum only over generated proposals, not over the coupled
path/label problem. Gap costs count skipped *positive peak groups*, never inferred
empty acquisition windows. `probability` is blank because this is MAP-only.

Node gains use the frozen scan detection probability and the native likelihood
ratio: sigma 200 Hz Gaussian signal density versus `2 / 4.4e6` uniform clutter
density. Native residuals are gated at 1000 Hz.

Run and test with the SciPy-capable pinned analysis environment described by the
parent report.

The reviewed continuity result is `outputs/assignments.csv`; the explicit
continuity-disabled control is `outputs/assignments-no-continuity.csv`. A
held-out/location Stage B has not been run.

The later matched fixed-position RF sensitivity control is under `rf-fitted-c/`
and `rf-zero-c/`, with its compact comparison in `rf-control-summary.json`.
It reruns the same tracker budget after the parent experiment's converged timing
and RX nuisance refits; it is an in-sample frequency-fit control and provides no
evidence of improved localization. New isolated runs can use `--output-dir` (or
`DS13_TRACKLET_OUTPUT_DIR`) plus `--continuity-only` without overwriting primary
artifacts.
