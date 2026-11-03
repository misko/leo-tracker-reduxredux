# Free height improves prediction but fails the geographic gate

All four single-scan fits complete and qualify. Both starting points converge
to essentially the same height within each scan, but the scans disagree by
about 1.04km. This is not reliable antenna-altitude evidence.

| Scan | Fitted ellipsoidal height | Held gain | Original horizontal error | Free-height horizontal error |
|---|---:|---:|---:|---:|
| 0 | +552.77m | +27.467 nats | 765.072m | 2801.210m |
| 16 | -489.80m | +8.959 nats | 2153.140m | 1821.649m |

The frozen held-prediction gate passes. Subsequent geographic readout of the
already sealed training-selected endpoints fails the both-scan improvement
gate. The baseline remains unchanged. No height, bound, prior, or endpoint was
tuned using reference error. No cross-scan data pooling occurred.

The model retains full original causal candidate mixtures, per-track profiled
CFOs, independent Student-t4/100Hz errors and original timing treatment. Height
is a fourth geometric parameter within deliberately broad +/-1km diagnostic
bounds; neither solution touches those bounds. These bounds are not surveyed
site constraints. The free height may absorb model mismatch, and improved
held prediction does not authenticate its physical interpretation.

Two tests pass for four-dimensional derivatives, held-data isolation and exact
zero-height geometry parity. Original zero-height scores replay before fitting.
Verification checks source hashes, every receipt, numerical qualification,
highest-training-score selection and training/held score replay. Optimization
is not independently rerun. All four fits have 90-second caps, with no retries.

Independent measured antenna altitude remains relevant for a fixed-height
physical correction. These free-height results provide no substitute for it.

See [fit protocol](PROTOCOL.md), [all attempts and sealed selections](selections.json),
[held results](outcome.json), [geographic protocol](GEOGRAPHIC_PROTOCOL.md), and
[verified geographic readout](geographic.json).
