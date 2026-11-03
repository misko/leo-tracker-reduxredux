# Bounded competing-history prototype

`mht.py` performs joint row/satellite-exclusive assignment within each archived
positive-peak group and retains multiple global histories. Its only dynamic
state is a near-zero regularized OU residual offset per satellite and
receiver/channel lane (100 Hz stationary sigma, 30 s timescale); there is no
per-satellite slope or quadratic and no group-level seed ownership gate. This
OU prior is a diagnostic regularizer, not a validated physical prior.

This is frozen conditional replay, not held-out evaluation. The archive has no
empty detection opportunities, so a "miss" is only a satellite left
unassigned in a real positive group. Exact alias-period duplicate copies are
removed within group; there is no near-frequency merging. Edges use the shared
raw log-gain emission (native 200 Hz scale, visibility and 5-sigma gate).
Exported `probability` is a marginal over the retained, state-adjusted truncated
beam and is not a calibrated posterior.

Run `.venv/bin/python mht.py`, and `pytest -q test_mht.py` from this directory.
